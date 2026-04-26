import actions
import aiohttp
import asyncio
import base64
import config
import datafile
import events
from flask import abort, Blueprint, Flask, render_template, request, Response, send_file, stream_with_context
from flask_sock import Server, Sock
from gevent.pywsgi import WSGIServer
import inspect
import json
from markupsafe import Markup
import os
import pickle
import plugins
import requests
from simple_websocket.errors import ConnectionClosed
import threading
import traceback
import tronix
from typing import Callable, Sequence
import uuid
import websocket
from werkzeug.datastructures import Headers

HOST = "127.0.0.1"
PORT = 6742
SECRET_FILE = datafile.makepath("secret.txt")
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
                return "", 204
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

@coreinterface.get("/actions")
def actions_page():
    return render_template("actions.html")

@sock.route("/events", bp=coreapi)
def api_events(ws:Server):
    bucket = events.new_bucket()
    try:
        while ws.connected:
            bucket.wait()
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
    return "", 204

@coreapi.route("/configs", methods=["GET", "PUT"])
def api_configs():
    if request.method == "HEAD":
        return "", 204, {"MTIME":os.stat(config.CONFIG_FILE).st_mtime_ns}
    elif request.method == "PUT":
        data = request.get_json()
        config.write(data, path=config.CONFIG_FILE)
        return "", 204
    else:
        r = send_file(config.CONFIG_FILE)
        r.headers["MTIME"] = os.stat(config.CONFIG_FILE).st_mtime_ns
        return r

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
    return combined


@coreapi.post("/plugins/load")
def api_load_plugin():
    name = request.form["name"]
    plugin = plugins.shared_plugins_list.get(name, None)
    if plugin is None:
        return "", 404
    plugin.load(plugins.LoadEvent(plugins.shared_plugins_list, plugin, __pconfig_path, False, __host_addr, __remote_api_addr))
    return "", 204

@coreapi.post("/plugins/unload")
def api_unload_plugin():
    name = request.form["name"]
    plugin = plugins.shared_plugins_list.get(name, None)
    if plugin is None:
        return "", 404
    plugin.unload(plugins.UnloadEvent(plugins.shared_plugins_list, plugin, False, None))
    return "", 204

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

@coreapi.post("/action/script/check")
def api_actions_script_check():
    help_text = actions.check_script(request.get_data(True))
    if help_text is None:
        return "", 204
    else:
        return help_text, 200, {"Content-Type":"text/plain"}

@coreapi.get("/action/list")
def api_actions_list():
    return send_file(actions.ACTIONS_PATH)

@coreapi.route("/action", methods=["GET", "POST", "DELETE"])
def api_action_route():
    name = request.args["name"]
    if request.method == "POST":
        data:dict[str] = request.json
        if not isinstance(data, dict):
            return "", 400
        table = actions.load_action_table()
        action = table.get(name, None)
        if action is None:
            table[data.setdefault("name", name)] = action = actions.Action.__new__(actions.Action)
            data.setdefault("requested_values", {})
        action.__setstate__(data)
        actions.save_action_table(table)
        return "", 204
    elif request.method == "DELETE":
        table = actions.load_action_table()
        if name in table:
            del table[name]
            actions.save_action_table(table)
        return "", 204
    else: #GET
        action = actions.load_action_table().get(name, None)
        if action is None:
            return "", 400
        else:
            return action.__getstate__(), 200
        
def api_action_script_run():
    #TODO handle script exceptions
    data:dict[str] = request.get_json()
    rtype = data["type"]
    
    scope_s = data.get("scope", None)
    if isinstance(scope_s, str):
        scope = pickle.loads(base64.b64decode(scope_s.encode("utf-8")))
        if isinstance(scope, dict):
            for v in scope.values():
                if isinstance(v, tronix.script.ScriptVariable):
                    x = v.get()
                    x.type = tronix.script.wrap_python_type(x.type.inner)
    else:
        scope = None
    script = tronix.Script(data["script"], scope)

    if rtype == "run_iter":
        def gen():
            riter = actions.script_runner.run_iter(script, data["force_parse"], data["force_compile"])
            yield len(script.steps).to_bytes(8, byteorder="big", signed=False)
            for result in riter:
                if inspect.isawaitable(result):
                    result = asyncio.run(result)
                r_b = pickle.dumps(result)
                yield len(r_b).to_bytes(8, byteorder="big", signed=False)
                yield r_b
            scope_b = pickle.dumps(script.scope)
            yield len(scope_b).to_bytes(8, byteorder="big", signed=False)
            yield scope_b
        return gen
    elif rtype in ("run", "run_async"):
        asyncio.run(actions.script_runner.run_async(script, data["force_parse"], data["force_compile"]))
        return pickle.dumps(script.scope), 200, {"Content-Type": "application/octet-stream"}
    else:
        return "", 422


def remote_api_script_env_handler():
    import websocket

    def ws_on_open(ws):
        print("connected to script env switch")

    def ws_on_reconnect(ws):
        print("reconnected to script env switch")

    def ws_on_message(ws, msg:str|bytearray|memoryview):
        if isinstance(msg, memoryview):
            msg = msg.tobytes()
        data = json.loads(msg)
        _handle_env_switch_instruction(data)

    def ws_on_error(ws, e:Exception):
        if isinstance(e, (ConnectionRefusedError, ConnectionClosed)):
            print(f"script env switch error: ({type(e).__name__}):", e)
        else:
            print(f"script env switch error: error ({type(e).__name__}):")
            traceback.print_exception(e)

    def ws_on_close(ws, status_code, msg:str|bytearray|memoryview):
        print("disconnected from script env switch")

    wsa = websocket.WebSocketApp(
        f"ws{"s"*(__host_addr[1]==443)}:{__host_addr[0]}:{__host_addr[1]}/api/action/script/env-switch",
        on_open=ws_on_open, on_message=ws_on_message,
        on_error=ws_on_error, on_close=ws_on_close,
        on_reconnect=ws_on_reconnect
    )
    try:
        wsa.run_forever(reconnect=5)
    except KeyboardInterrupt:
        pass

_rapi_script_env_thread = threading.Thread(target=remote_api_script_env_handler, daemon=True)

_arl_queue:list[tuple[uuid.UUID, tronix.Script, str]] = []
_arl_loop = None
_arl_queue_lock = threading.Lock()
_arl_ready = asyncio.Event()

_arl_futures:dict[uuid.UUID, asyncio.Future] = {}
_arl_futures_lock = asyncio.Lock()

_arl_done:dict[str,list[tuple[uuid.UUID, bool]]] = {}
_arl_done_lock = threading.Lock()

async def _arl_future(uid:uuid.UUID, queued:list[tuple[uuid.UUID, tronix.Script, str]]):
    try:
        results = await actions.run_scripts(*queued)
        with _arl_done_lock:
            for uid, success, env, *_ in results:
                _arl_done[env] = (uid, success)
    finally:
        async with _arl_futures_lock:
            _arl_futures.pop(uid, None)

async def action_runner_local_loop():
    while True:
        await _arl_ready.wait()
        with _arl_queue_lock:
            queued = _arl_queue.copy()
            _arl_queue.clear()
            _arl_ready.clear()
        uid = uuid.uuid4()
        async with _arl_futures_lock:
            _arl_futures[uid] = asyncio.ensure_future(_arl_future(uid, queued), loop=_arl_loop)

def action_runner_local_handler():
    global _arl_loop
    _arl_loop = loop = asyncio.new_event_loop()
    loop.run_until_complete(action_runner_local_loop())

_arl_thread = threading.Thread(target=action_runner_local_handler, daemon=True)
def start_action_runner_local():
    _arl_thread.start()
    return _arl_thread

def _handle_env_switch_instruction(data:dict[str]):
    instruction = data["instruction"]
    print("script env switch got instruction:", instruction)
    if instruction == "run":
        scripts = data.get("scripts",None)
        if isinstance(scripts, list):
            add_run = []
            for sdata in scripts:
                if not isinstance(sdata, dict):
                    continue
                env = sdata["env"]
                if env is None:
                    continue
                elif env == actions.current_environment_name:
                    script = sdata["script"]
                    if isinstance(script, dict):
                        uid = uuid.UUID(sdata["uid"])
                        scope = pickle.loads(base64.b64decode(script["scope"]))
                        s = tronix.Script(script["content"], scope)
                        add_run.append((uid, s, env))
                else:
                    uid = uuid.UUID(sdata["uid"])
                    script = sdata["script"]
                    with actions._env_switch_queue_lock:
                        q = actions._env_switch_queue.get(env,None)
                        if q is None:
                            actions._env_switch_queue[env] = q = []
                        actions._env_switch_done[uid] = done_entry = actions._env_switch_done_entry(_arl_loop)
                        q.append((uid, env, script, done_entry)) #NOTE idk if i wanna be making a _env_switch_done_entry here
            if add_run:
                with _arl_queue_lock:
                    _arl_queue.extend(add_run)
                    _arl_loop.call_soon_threadsafe(_arl_ready.set)
    elif instruction == "done":
        scripts = data.get("scripts",None)
        if isinstance(scripts, dict):
            for id_s, success in scripts.items():
                uid = uuid.UUID(id_s)
                de = actions._env_switch_done.get(uid,None)
                if de is not None:
                    de.mark_done(bool(success))
    elif instruction == "error":
        ...

def sock_action_environment_switch(ws:Server):
    environment_name = request.args["name"]
    with actions._env_switch_queue_lock:
        if environment_name in actions._env_switch_queue:
            ws.close(4422, f"environment name already in use: {environment_name}")
            return
        _esq = actions._env_switch_queue[environment_name] = []
    with _arl_done_lock:
        _arldq = _arl_done[environment_name] = []
    print("script environment", environment_name, "connected to the switch")
    try:
        while ws.connected:
            msg = ws.receive(0.001)
            if isinstance(msg, (str, bytes)):
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    print("script env switch:\tmessage invalid json:", msg)
                else:
                    if isinstance(data, dict):
                        try:
                            _handle_env_switch_instruction(data)
                        except Exception as e:
                            traceback.print_exception(e)
            if _esq:
                with actions._env_switch_queue_lock:
                    _esq = q = actions._env_switch_queue.get(environment_name,None)
                    if q:
                        ws.send(json.dumps({
                            "instruction": "run",
                            "scripts": [
                                {
                                    "uid": str(uid),
                                    "env": env_name,
                                    "script": {
                                        "content": s.raw,
                                        "scope": _scope_to_b64(s.scope)
                                    } if isinstance(s, tronix.Script) else s
                                } for uid, env_name, s, *_ in q
                            ]
                        }))
                        q.clear()
            if _arldq:
                with _arl_done_lock:
                    _arldq = q = _arl_done.get(environment_name,None)
                    if q:
                        ws.send(json.dumps({
                            "instruction": "done",
                            "scripts": {
                                str(uid): success
                                for uid, success in q
                            }
                        }))
                        q.clear()
    except KeyboardInterrupt:
        pass
    finally:
        if ws.connected:
            ws.close()
        with actions._env_switch_queue_lock:
            actions._env_switch_queue.pop(environment_name,None)
        with _arl_done_lock:
            _arl_done.pop(environment_name,None)
        

def _scope_to_b64(scope):
    return base64.b64encode(pickle.dumps(scope)).decode("utf-8") if scope else None

class ProxyScriptRunner(tronix.utils.ScriptRunner):

    @staticmethod
    def update_scope(runner:tronix.utils.ScriptRunner, script:tronix.Script):
        if isinstance(runner, ProxyScriptRunner) and script._hash in runner.scopes:
            scope_b = runner.scopes[script._hash]
            scope = script.scope = pickle.loads(scope_b)
            if isinstance(scope, dict):
                for v in scope.values():
                    if isinstance(v, tronix.script.ScriptVariable):
                        x = v.get()
                        x.type = tronix.script.wrap_python_type(x.type.inner)
            return True
        return False
    
    def __init__(self, remote_api_addr:str, secure:bool=False):
        super().__init__()
        self.remote_api_addr = remote_api_addr
        self.secure = secure
        self.session = requests.Session()
        self.scopes:dict[bytes,bytes|None] = {}

    def _prep_req(self, session:aiohttp.ClientSession|requests.Session, rtype:str, script:tronix.Script|str, force_parse:bool, force_compile:bool):
        if isinstance(script, tronix.Script):
            if script.scope:
                scope_b = pickle.dumps(script.scope)
                scope = base64.b64encode(scope_b).decode("utf-8")
            else:
                scope = scope_b = None
            h = script._hash
            script = script.raw
        else:
            h = tronix.Script.HASH_FUNC(script.encode("utf-8"), usedforsecurity=False).digest()
            scope = scope_b = None
        
        self.scopes[h] = scope_b

        return session.post(f"http{"s"*self.secure}://{self.remote_api_addr}/api/action/run-proxied", json={
            "type": rtype,
            "script": script,
            "scope": scope,
            "force_parse": force_parse,
            "force_compile": force_compile
        }), h

    def run_iter(self, script:tronix.Script|str, force_parse:bool=False, force_compile:bool=False):
        r, h = self._prep_req(self.session, "run_iter", script, force_parse, force_compile)
        if not r.ok:
            ... #TODO handle not ok
        count_b = r.raw.read(8)
        if not count_b:
            return
        count = int.from_bytes(count_b, byteorder="big", signed=False)
        for _ in range(count):
            size_b = r.raw.read(8)
            if not size_b:
                return
            size = int.from_bytes(size_b, byteorder="big", signed=False)
            obj_b = r.raw.read(size)
            if not obj_b:
                ... #TODO error
            yield pickle.loads(obj_b)
        scopelen_b = r.raw.read(8)
        if not scopelen_b:
            return
        scopelen = int.from_bytes(scopelen_b, byteorder="big", signed=False)
        if scopelen:
            scope_b = r.raw.read(scopelen)
            if not scope_b:
                ... #TODO error
        else:
            scope_b = None
        self.scopes[h] = scope_b
    
    def run(self, script:tronix.Script|str, force_parse:bool=False, force_compile:bool=False):
        r, h = self._prep_req(self.session, "run", script, force_parse, force_compile)
        if not r.ok:
            ... #TODO handle not ok
        scope_b = r.content
        self.scopes[h] = scope_b if scope_b else None

    async def run_async(self, script:tronix.Script|str, force_parse:bool=False, force_compile:bool=False):
        async with aiohttp.ClientSession(cookies=requests.utils.dict_from_cookiejar(self.session.cookies), headers=self.session.headers, auth=self.session.auth) as s:
            rctx, h = self._prep_req(s, "run_async", script, force_parse, force_compile)
            async with rctx as r:
                if not r.ok:
                    ... #TODO handle not ok
                scope_b = await r.read()
                self.scopes[h] = scope_b if scope_b else None
        
            

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
                        msg = ws.receive()
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
                if isinstance(e, (ConnectionRefusedError, ConnectionClosed)):
                    print(f"PROXY WS ERROR ({url}) {type(e).__name__}: {e}")
                else:
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


def attach_core(interface_mode:str, api_mode:str, tronix_mode:str, remote_api_addr:str|None=None):
    global __remote_api_addr
    __remote_api_addr = remote_api_addr
    if interface_mode == plugins.COMPONENT_MODE_NORMAL:
        app.register_blueprint(coreinterface)
    elif interface_mode == plugins.COMPONENT_MODE_REMOTE:
        create_component_proxy(remote_api_addr, app, "proxy_core_interface", socket=False)

    tronix_enabled = tronix_mode in (plugins.COMPONENT_MODE_NORMAL, plugins.COMPONENT_MODE_REMOTE)

    if api_mode == plugins.COMPONENT_MODE_NORMAL:
        if tronix_enabled:
            coreapi.post("/action/script/run")(api_action_script_run)
            sock.route("/action/script/env-switch", bp=api)(sock_action_environment_switch)
        api.register_blueprint(coreapi)
    elif api_mode == plugins.COMPONENT_MODE_REMOTE:
        vcoreapi = Blueprint("proxy_core_api", __name__)
        if tronix_enabled:
            _rapi_script_env_thread.start()
        for p in ["/configs", "/configs/meta", "/plugins/load", "/plugins/unload", "/events/dispatch", "/action/script/check", "/action/script/run", "/action/list", "/action"]:
            create_endpoint_proxy(remote_api_addr, [p], vcoreapi, socket=False, endpoint_name=p[1:].replace("/", "_"))
        create_endpoint_proxy(remote_api_addr, ["/events", "/account/script/env-switch"], vcoreapi, normal=False, endpoint_name="events")
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
