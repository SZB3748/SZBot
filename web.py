import config
import events
from flask import abort, Blueprint, Flask, render_template, request, send_file
from flask_sock import Server, Sock
from gevent.pywsgi import WSGIServer
import json
from markupsafe import Markup
import plugins
import requests
from typing import Callable

HOST = "127.0.0.1"
PORT = 6742
SECRET_FILE = "secret.txt"

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
    combined = {}
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
    plugin.load((plugins.shared_plugins_list, plugin, False, app, api, sock))
    return "", 200

@api.post("/plugins/unload")
def api_unload_plugin():
    name = request.form["name"]
    plugin = plugins.shared_plugins_list.get(name, None)
    if plugin is None:
        return "", 404
    plugin.unload((plugins.shared_plugins_list, plugin, False, None))
    return "", 200


def serve():
    app.register_blueprint(api)
    server = WSGIServer((HOST, PORT), app)
    server.serve_forever()
