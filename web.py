import config
import events
from flask import abort, Blueprint, Flask, render_template, request, Response, send_file, stream_with_context
from flask_sock import Server, Sock
from gevent.pywsgi import WSGIServer
import json
from markupsafe import Markup
import plugins
import requests
import threading
import traceback
from typing import Callable, Sequence
import websocket
from werkzeug.datastructures import Headers

HOST = "127.0.0.1"
PORT = 6742
SECRET_FILE = "secret.txt"
API_PROXY_BUFFER_SIZE = 8192

DEFAULT_STYLES_FONT = "\"Fragment Mono\""
DEFAULT_STYLES_BG_COLOR = "#000"
DEFAULT_STYLES_TEXT_COLOR = "#fff"
DEFAULT_STYLES_FG_COLOR = "#7f0"
DEFAULT_STYLES_FG2_COLOR = "#041f00"
DEFAULT_STYLES = f"""\
    font-family: {DEFAULT_STYLES_FONT};
    background-color: {DEFAULT_STYLES_BG_COLOR};
    color: {DEFAULT_STYLES_TEXT_COLOR};
    --color-fg: {DEFAULT_STYLES_FG_COLOR};
    --color-fg2: {DEFAULT_STYLES_FG2_COLOR};"""

def build_styles_from_config()->str:
    c = config.read()
    style = c.get("Style", None)
    if isinstance(style, dict):
        fonts_r = style.get("fonts", None)
        if fonts_r is None:
            fonts = DEFAULT_STYLES_FONT
        elif isinstance(fonts_r, str):
            fonts = fonts_r
        elif isinstance(fonts_r, list):
            fonts_items = []
            for item in fonts_r:
                if isinstance(item, str):
                    if " " in item and not ("\"" in item or "'" in item):
                        fonts_items.append(f"\"{item}\"")
                    else:
                        fonts_items.append(item)
            fonts = ", ".join(fonts_items)
        css_styles = [
            "font-family", fonts,
            "background-color", style.get("background_color", DEFAULT_STYLES_BG_COLOR),
            "color", style.get("text_color", DEFAULT_STYLES_TEXT_COLOR),
            "--color-fg", style.get("primary_foreground_color", None) or DEFAULT_STYLES_FG_COLOR,
            "--color-fg2", style.get("secondary_foreground_color", None) or DEFAULT_STYLES_FG2_COLOR,
        ]
        return "\n    ".join(f"{css_styles[i]}: {css_styles[i+1]};" for i in range(0, len(css_styles), 2))
    else:
        return DEFAULT_STYLES
    

def load_config_styles_css()->str:
    loaded = build_styles_from_config()
    return Markup(f"""\
<style>
:root, body {{
    {loaded}
}}
</style>""")

__host_addr = None
__remote_api_addr = None
__api_only = None

def serve_when_loaded(loaded_callback:Callable[[], bool], unloaded_error_code:int=404):
    def decor(f:Callable):
        def wrapper(*args, **kwargs):
            if loaded_callback():
                return f(*args, **kwargs)
            elif unloaded_error_code:
                abort(unloaded_error_code)
            else: # ==0
                return "", 200
        wrapper.__name__ = f.__name__
        wrapper.__doc__ = f.__doc__
        return wrapper
    return decor


app = Flask(__name__)
api = Blueprint("api", __name__, url_prefix="/api")
app.jinja_env.globals["load_config_styles"] = load_config_styles_css
app.url_map.strict_slashes = False
app.jinja_env.auto_reload = True
app.config["TEMPLATES_AUTO_RELOAD"] = True
with open(SECRET_FILE) as f:
    app.secret_key = f.read()
sock = Sock(app)

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/oauth")
def oauth():
    code = request.args["code"]
    configs = config.read(path=config.OAUTH_TWITCH_FILE)
    r = requests.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": configs["Client-Id"],
        "client_secret": configs["Client-Secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": request.base_url
    })
    if not r.ok:
        print("oauth failure")
        return r.text, r.status_code
    d = r.json()
    config.write(config_updates={"Token": d["access_token"], "Refresh-Token": d["refresh_token"]}, path=config.OAUTH_TWITCH_FILE)
    return "Restart", 200

@app.get("/configs")
def configs_page():
    return render_template("configs.html")

@sock.route("/events", bp=api)
def api_events(ws:Server):
    bucket = events.new_bucket()
    try:
        while ws.connected:
            ws.receive(0)
            for event in bucket.dump():
                ws.send(event.to_json())
    except KeyboardInterrupt:
        ws.close()
    finally:
        events.remove_bucket(bucket)

@api.route("/configs", methods=["GET", "PUT"])
def api_configs():
    if request.method == "PUT":
        data = request.get_json()
        config.write(data, path=config.CONFIG_FILE)
        return "", 200
    else:
        return send_file(config.CONFIG_FILE)

@api.get("/configs/meta")
def api_configs_meta():
    combined = {"": plugins.CORE_CONFIGS_META}
    for name, plugin in plugins.shared_plugins_list.items(): #if plugins.shared_plugins_list is None, raises an AttributeError and results in a 500
        if plugin.module is not None: #is enabled
            meta_type, meta_value = plugin.meta_target
            if meta_type == "path":
                with open(meta_value) as f:
                    combined[name] = json.load(f)
            elif meta_type == "inline":
                combined[name] = meta_value
    
    return combined


@api.post("/plugins/load")
def api_load_plugin():
    name = request.form["name"]
    plugin = plugins.shared_plugins_list.get(name, None)
    if plugin is None:
        return "", 404
    plugin.load((plugins.shared_plugins_list, plugin, False, __host_addr, __remote_api_addr, __api_only))
    return "", 200

@api.post("/plugins/unload")
def api_unload_plugin():
    name = request.form["name"]
    plugin = plugins.shared_plugins_list.get(name, None)
    if plugin is None:
        return "", 404
    plugin.unload((plugins.shared_plugins_list, plugin, False, None))
    return "", 200

class proxy_headers:
    def __init__(self, base:Headers, exclude:Sequence[str], exclude_prefix:tuple[str, ...]=()):
        self.base = base
        self.exclude = exclude
        self.exclude_prefix = exclude_prefix

    def items(self):
        for k, v in self.base.items():
            kl = k.lower()
            if kl in self.exclude or kl.startswith(self.exclude_prefix):
                continue
            yield k, v

_SECURE_PROTOCOLS = {"https", "wss"}
def process_remote_api(remote_api_addr:str|None)->tuple[str|None, bool]:
    if remote_api_addr is None:
        return None, False
    
    schemeIndex = remote_api_addr.find("://")
    pathIndex = remote_api_addr.find("/")
    if schemeIndex >= 0:
        scheme = remote_api_addr[:schemeIndex]
        secure_scheme = scheme.strip().lower() in _SECURE_PROTOCOLS
    else:
        secure_scheme = False
    remote_api_addr = remote_api_addr[schemeIndex+1:(len(remote_api_addr) if pathIndex < 0 else pathIndex)].strip().lower()
    # using localhost can cause significant slowdowns for the
    # API proxy on Windows. cite: https://stackoverflow.com/a/75425128
    if remote_api_addr.startswith("localhost:"):
        remote_api_addr = remote_api_addr.replace("localhost", "127.0.0.1", 1)
    return remote_api_addr, secure_scheme or remote_api_addr.split(":",1) == "443"

def serve(host:str=HOST, port:int=PORT, remote_api_addr:str=None, api_only=False):
    global __host_addr, __remote_api_addr, __api_only

    __host_addr = host, port
    __remote_api_addr = remote_api_addr
    __api_only = api_only

    if remote_api_addr is not None:
        vapi = Blueprint("api", __name__, url_prefix="/api")
        
        processed_api_addr, secure = process_remote_api(remote_api_addr)

        s = "s" * secure
        proxy_host = f"http{s}://{processed_api_addr}/"
        proxy_host_ws = f"ws{s}://{processed_api_addr}/"
        
        EXCLUDE_SOCK_HEADERS = {"host", "upgrade", "connection"}
        @sock.route("/", defaults={"path": ""}, bp=vapi)
        @sock.route("/<path:path>", bp=vapi)
        def api_ws_proxy(ws:Server, path:str):
            print(f"PROXY WS: /api/{path}")
            def send_to_remote():
                try:
                    while ws.connected and client.keep_running:
                        msg = ws.receive(0)
                        if msg is not None:
                            client.send(msg, websocket.ABNF.OPCODE_BINARY if isinstance(msg, bytes) else websocket.ABNF.OPCODE_TEXT)
                except KeyboardInterrupt:
                    ws.close()
                finally:
                    client.close()
            
            send_thread = threading.Thread(target=send_to_remote, daemon=True)

            def on_open(cws:websocket.WebSocket):
                send_thread.start()

            def on_message(cws:websocket.WebSocket, msg:str|bytearray|memoryview):
                if isinstance(msg, memoryview):
                    msg = msg.tobytes()
                elif isinstance(msg, bytearray):
                    msg = bytes(msg)
                ws.send(msg)

            def on_error(cws:websocket.WebSocket, e:Exception):
                traceback.print_exception(e)

            def on_close(cws:websocket.WebSocket, status_code, reason):
                ws.close(status_code, reason)

            client = websocket.WebSocketApp(
                url=request.url.replace(request.host_url, proxy_host_ws, 1),
                header=[
                    f"{k}: {v}" for k,v in request.headers.items()
                    if (kl := k.lower()) not in EXCLUDE_SOCK_HEADERS and not kl.startswith("sec-websocket-")
                ],
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            client.run_forever()

        methods = ["GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"]
        @vapi.route("/", methods=methods, defaults={"path": ""})
        @vapi.route("/<path:path>", methods=methods)
        def api_proxy(path:str):
            print(f"PROXY: /api/{path}")
            resp = requests.request(
                method=request.method,
                url=request.url.replace(request.host_url, proxy_host, 1),
                headers=proxy_headers(request.headers, ("host",)),
                data=request.get_data(),
                cookies=request.cookies,
                allow_redirects=False,
                stream=True
            )
            excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
            headers = [(n, v) for n, v in resp.raw.headers.items() if n.lower() not in excluded_headers]
            
            return Response(stream_with_context(resp.iter_content(chunk_size=API_PROXY_BUFFER_SIZE)), resp.status_code, headers)
    else:
        vapi = api

    if api_only:
        #make a new Flask object, only keeping the api.* endpoints
        vapp = Flask(__name__,
                static_url_path=app.static_url_path, static_folder=app.static_folder, subdomain_matching=app.subdomain_matching,
                template_folder=app.template_folder, instance_path=app.instance_path, root_path=app.root_path
        )
        vapp.jinja_env.globals.update(app.jinja_env.globals)
        vapp.jinja_env.auto_reload = app.jinja_env.auto_reload
        vapp.config.update(app.config)
        vapp.url_map.strict_slashes = app.url_map.strict_slashes
        vapp.secret_key = app.secret_key
        for rule in app.url_map.iter_rules():
            if rule.endpoint.startswith("api.") or rule.endpoint == "api":
                vapp.url_map.add(rule)
    else:
        vapp = app

    vapp.register_blueprint(vapi)
    server = WSGIServer((host, port), vapp)
    server.serve_forever()
