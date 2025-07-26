import config
import events
from flask import abort, Blueprint, Flask, render_template, request, Response, send_file, stream_with_context
from flask_sock import Server, Sock
from gevent.pywsgi import WSGIServer
import inspect
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
DEFAULT_STYLES_BG_COLOR = "#000000"
DEFAULT_STYLES_TEXT_COLOR = "#ffffff"
DEFAULT_STYLES_FG_COLOR = "#77ff00"
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
__pconfig_path = None

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
coreinterface = Blueprint("core_interface", __name__)
coreapi = Blueprint("core_api", __name__)
app.jinja_env.globals["load_config_styles"] = load_config_styles_css
app.url_map.strict_slashes = False
app.jinja_env.auto_reload = True
app.config["TEMPLATES_AUTO_RELOAD"] = True
with open(SECRET_FILE) as f:
    app.secret_key = f.read()
sock = Sock(app)

@coreinterface.get("/")
def index():
    return render_template("index.html")

@app.get("/oauth")
def oauth():
    code = request.args["code"]
    oauth = config.read(path=config.OAUTH_TWITCH_FILE)
    identity:dict = oauth["identity"]
    client_id = identity["Client-Id"]
    r = requests.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": client_id,
        "client_secret": identity["Client-Secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": request.base_url
    })
    if not r.ok:
        print("oauth failure")
        return r.text, r.status_code
    d = r.json()
    token = d["access_token"]
    refresh = d["refresh_token"]
    r2 = requests.get("https://api.twitch.tv/helix/users", headers={"Client-Id": client_id, "Authorization": f"Bearer {token}"})
    if not r2.ok:
        print("user identify failure")
        return r2.text, r2.status_code
    u = r2.json()
    login = u["data"][0]["login"]
    if login == str(identity["Bot-Name"]).lower():
        identity.update({"Token": token, "Refresh-Token": refresh})
        config.write(config_updates={"identity": identity}, path=config.OAUTH_TWITCH_FILE)
        return "Authenticated bot identity, restart bot.", 200
    else:
        channels = oauth.get("channels",None)
        tdata = {"token": token, "refresh_token": refresh}
        if isinstance(channels, dict):
            channels[login] = tdata
        else:
            channels = {login: tdata}
        config.write(config_updates={"channels": channels}, path=config.OAUTH_TWITCH_FILE)
        return "Authenticated user channel, you can close this tab.", 200

@coreinterface.get("/configs")
def configs_page():
    return render_template("configs.html")

@sock.route("/events", bp=coreapi)
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

@coreapi.post("/events/dispatch")
def api_events_dispatch():
    batch:list[dict[str]] = json.loads(request.form["batch"])
    if not isinstance(batch, list):
        return "", 422
    events.dispatch(*(events.Event(**data) for data in batch if isinstance(data, dict)))
    return "", 200

@coreapi.route("/configs", methods=["GET", "PUT"])
def api_configs():
    if request.method == "PUT":
        data = request.get_json()
        config.write(data, path=config.CONFIG_FILE)
        return "", 200
    else:
        return send_file(config.CONFIG_FILE)

@coreapi.get("/configs/meta")
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
    from pprint import pprint
    pprint(combined)
    return combined


@coreapi.post("/plugins/load")
def api_load_plugin():
    name = request.form["name"]
    plugin = plugins.shared_plugins_list.get(name, None)
    if plugin is None:
        return "", 404
    plugin.load(plugins.LoadEvent(plugins.shared_plugins_list, plugin, __pconfig_path, False, __host_addr, __remote_api_addr))
    return "", 200

@coreapi.post("/plugins/unload")
def api_unload_plugin():
    name = request.form["name"]
    plugin = plugins.shared_plugins_list.get(name, None)
    if plugin is None:
        return "", 404
    plugin.unload(plugins.UnloadEvent(plugins.shared_plugins_list, plugin, False, None))
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


def create_endpoint_proxy(addr:str, routes:list[str], bp:Blueprint, normal=True, socket=True, endpoint_name:str|None=None):
    processed_api_addr, secure = process_remote_api(addr)

    s = "s" * secure
    proxy_host = f"http{s}://{processed_api_addr}/"
    proxy_host_ws = f"ws{s}://{processed_api_addr}/"

    if socket:
        EXCLUDE_SOCK_HEADERS = {"host", "upgrade", "connection"}
        def ws_proxy(ws:Server, path:str):
            url = request.url.replace(request.host_url, proxy_host_ws, 1)
            print("PROXY WS:", url)
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
                print(f"PROXY WS ERROR ({url}):")
                traceback.print_exception(e)

            def on_close(cws:websocket.WebSocket, status_code, reason):
                ws.close(status_code, reason)

            client = websocket.WebSocketApp(
                url=url,
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

        if endpoint_name is not None:
            ws_proxy.__name__ = endpoint_name

        if routes:
            for i in range(len(routes)-1, 0, -1):
                ws_proxy = sock.route(routes[i], bp=bp)(ws_proxy)
            ws_proxy = sock.route(routes[0], bp=bp, defaults={"path": ""})(ws_proxy)

    if normal:
        methods = ["GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"]
        def normal_proxy(path:str):
            url = request.url.replace(request.host_url, proxy_host, 1)
            print("PROXY:", url)
            resp = requests.request(
                method=request.method,
                url=url,
                headers=proxy_headers(request.headers, ("host",)),
                data=request.get_data(),
                cookies=request.cookies,
                allow_redirects=False,
                stream=True
            )
            excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
            headers = [(n, v) for n, v in resp.raw.headers.items() if n.lower() not in excluded_headers]
            
            return Response(stream_with_context(resp.iter_content(chunk_size=API_PROXY_BUFFER_SIZE)), resp.status_code, headers)
        
        if endpoint_name is not None:
            normal_proxy.__name__ = endpoint_name

        if routes:
            for i in range(len(routes)-1, 0, -1):
                normal_proxy = bp.route(routes[i], methods=methods)(normal_proxy)
            normal_proxy = bp.route(routes[0], methods=methods, defaults={"path": ""})(normal_proxy)
    
def add_bp_if_new(t:Flask|Blueprint, bp:Blueprint):
    if isinstance(t, Flask):
        it = t.blueprints.values()
    else:
        it = (b for b, _ in t._blueprints)

    for b in it:
        if b == bp:
            return False
    t.register_blueprint(bp)
    return True

def create_component_proxy(address:str, dest:Flask|Blueprint, bpname:str, prefix:str|None=None, proxy_routes=["/", "/<path:path>"], normal:bool=True, socket:bool=True):
    frame = inspect.currentframe()
    iname = __name__
    if frame is not None:
        frame = frame.f_back
        if frame is not None:
            iname = frame.f_globals["__name__"]
    vbp = Blueprint(bpname, iname, url_prefix=prefix)
    create_endpoint_proxy(address, proxy_routes, vbp, normal=normal, socket=socket)
    add_bp_if_new(dest, vbp)


def attach_core(interface_mode:str, api_mode:str, remote_api_addr:str|None=None):
    global __remote_api_addr
    __remote_api_addr = remote_api_addr
    if interface_mode == plugins.COMPONENT_MODE_NORMAL:
        app.register_blueprint(coreinterface)
    elif interface_mode == plugins.COMPONENT_MODE_REMOTE:
        create_component_proxy(remote_api_addr, app, "proxy_core_interface", socket=False)

    if api_mode == plugins.COMPONENT_MODE_NORMAL:
        api.register_blueprint(coreapi)
    elif api_mode == plugins.COMPONENT_MODE_REMOTE:
        vcoreapi = Blueprint("proxy_core_api", __name__)
        for p in ["/configs", "/configs/meta", "/plugins/load", "/plugins/unload", "/events/dispatch"]:
            create_endpoint_proxy(remote_api_addr, [p], vcoreapi, socket=False, endpoint_name=p[1:].replace("/", "_"))
        create_endpoint_proxy(remote_api_addr, ["/events"], vcoreapi, normal=False, endpoint_name="events")
        api.register_blueprint(vcoreapi)
        #replace default_container.dispatch so that all events for the default event system get sent to the remote instance
        def proxy_dispatch(*e:events.Event):
            batch = [{"name":event.name, "data":event.data} for event in e]
            r = requests.post(f"http{"s"*(__host_addr[1]==443)}://{__host_addr[0]}:{__host_addr[1]}/api/events/dispatch", data={"batch":json.dumps(batch)})
            r.raise_for_status()
        events.default_container.dispatch = proxy_dispatch


def serve(host:str=HOST, port:int=PORT, pconfig_path:str=config.PLUGIN_FILE):
    global __host_addr, __pconfig_path

    __host_addr = host, port
    __pconfig_path = pconfig_path

    app.register_blueprint(api)
    server = WSGIServer((host, port), app)
    server.serve_forever()
