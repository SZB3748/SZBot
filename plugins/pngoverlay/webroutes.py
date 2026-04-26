from . import medialist, statemapping
import config
import datafile
from datetime import datetime, timedelta, timezone
import events
from flask import Blueprint, Flask, render_template, request, send_file
import json
import os
import plugins
import shutil
import threading
import traceback
from web import add_bp_if_new, serve_when_loaded, sock
from werkzeug.security import safe_join

DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(DIR, "static")
TEMPATES_DIR = os.path.join(DIR, "templates")
STATEMAP_SEND_COOLDOWN = timedelta(seconds=2.5)

STATEMAP_FILE = datafile.makepath("pngbinds.json")

web_loaded = False
web_loaded_callback = lambda: web_loaded

meta:plugins.Meta = None
nav_stack:statemapping.NavigatorStackFrame = None
statemap:statemapping.StateMap = None
event_negotiator:statemapping.EventNegotiator = None
event_negotiator_thread:threading.Thread = None
last_statemap_send = datetime.now()

keybinds_keylisteners:events.EventListenerCollection = None

def _get_state_data(frame:statemapping.NavigatorStackFrame|None)->dict[str]:
    event = None if event_negotiator is None else event_negotiator.get_first_active()
    if frame is not None:
        state = frame.state
        if event is not None and state.allow_event_interrupt:
            data_name = event.state_name()
            data_media = event.media.__getstate__()
        else:
            data_name = state.name
            data_media = state.media.__getstate__()
    elif event is not None:
        data_name = event.state_name()
        data_media = event.media.__getstate__()
    else:
        data_name = data_media = None
    return {"name": data_name, "media": data_media}

def dispatch_state_change_event():
    events.dispatch(events.Event("pngbinds:state_change", _get_state_data(nav_stack)))

def get_config_default_state(meta:plugins.Meta)->str|None:
    config_parent = plugins.read_configs(config.CONFIG_FILE, meta)
    c:dict = config_parent.get("PNG-Binds", None)
    if c is not None:
        return c.get("Default-State", None)
    return None

def load_statemap():
    if os.path.isfile(STATEMAP_FILE):
        with open(STATEMAP_FILE) as f:
            return statemapping.StateMap.load(f)
    return statemapping.StateMap()

def listen_remote_events_keys(host:str, secure:bool):
    from simple_websocket.errors import ConnectionClosed
    import websocket

    def ws_on_open(ws):
        print("connected to keybinds keys")

    def ws_on_reconnect(ws):
        print("reconnected to keybinds keys")

    def ws_on_message(ws, msg:str|bytearray|memoryview):
        if isinstance(msg, memoryview):
            msg = msg.tobytes()
        data = json.loads(msg)
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            print("pngoverlay:\t keybinds events message invalid json:", msg)
        else:
            if isinstance(data, dict) and isinstance((event_name := data.get("name", None)), str):
                event = events.Event(event_name, data.get("data"))
                keybinds_keylisteners.handle_event(event)

    def ws_on_error(ws, e:Exception):
        if isinstance(e, (ConnectionRefusedError, ConnectionClosed)):
            print(f"keybinds keys error: ({type(e).__name__}):", e)
        else:
            print(f"keybinds keys error: error ({type(e).__name__}):")
            traceback.print_exception(e)

    def ws_on_close(ws, status_code, msg:str|bytearray|memoryview):
        print("disconnected from keybinds keys")

    print("pngoverlay: connecting to remote keybinds keys")
    wsa = websocket.WebSocketApp(f"ws{"s"*secure}://{host}/api/keybinds/events/keys",
                                 )

pngoverlaypages_parent = Blueprint("pngoverlayparent", __name__, static_folder=STATIC_DIR, static_url_path="/static/pngoverlay")
pngoverlaypages = Blueprint("pngoverlay", __name__, url_prefix="/pngoverlay", template_folder=TEMPATES_DIR)
pngoverlayoverlays = Blueprint("pngoverlayoverlays", __name__, url_prefix="/pngoverlay/overlay", template_folder=TEMPATES_DIR)
pngoverlayapi = Blueprint("pngoverlayapi", __name__, url_prefix="/pngoverlay")

@pngoverlayapi.route("/statemap.json", methods=["GET", "PUT"])
@serve_when_loaded(web_loaded_callback)
def statemap_file():
    if request.method == "PUT":
        statemap = statemapping.StateMap.__new__(statemapping.StateMap)
        try:
            statemap.__setstate__(request.get_json())
        except (KeyError, TypeError, AttributeError) as e:
            traceback.print_exception(e)
            return "", 422
        with open(STATEMAP_FILE, "w") as f:
            statemap.dump(f, indent="    ")
        return "", 200
    elif os.path.isfile(STATEMAP_FILE):
        return send_file(STATEMAP_FILE)
    else:
        return {}

@pngoverlayapi.get("/media/list")
@serve_when_loaded(web_loaded_callback)
def get_media_list():
    return medialist.load_media_list()

@pngoverlayapi.route("/media/file/<name>", methods=["GET", "POST", "DELETE"])
@serve_when_loaded(web_loaded_callback)
def get_media_file(name:str):
    if request.method == "POST":
        mtype = request.form.get("type", None)
        if mtype is None:
            mtype = "image"
        else:
            mtype = mtype.lower()
        
        if mtype == "image":
            file = request.files["file"]
            value = safe_join(medialist.MEDIA_DIR, file.filename)
            with open(value, "wb") as f:
                shutil.copyfileobj(file, f)
        elif mtype == "iframe":
            value = request.form["value"]
        entry = {
            "value": value,
            "type": mtype
        }

        mlist = medialist.load_media_list()
        if name in mlist:
            mlist[name].update(entry)
        else:
            mlist[name] = entry
        medialist.save_media_list(mlist)
        return "", 200
    elif request.method == "DELETE":
        mlist = medialist.load_media_list()
        entry = mlist.get(name, None)
        if entry is not None:
            mtype = entry.get("type", None)
            value = entry.get("value", None)
            if mtype == "image":
                if value is not None and os.path.isfile(value):
                    os.remove(value)
            del mlist[name]
            medialist.save_media_list(mlist)
            return "", 200
        return "", 404
    else:
        mlist = medialist.load_media_list()
        m = mlist.get(name, None)
        if m is not None:
            mtype = m.get("type", None)
            if mtype == "image":
                mpath:str = m["value"]
                if os.path.isfile(mpath):
                    return send_file(mpath)
            elif mtype == "iframe":
                return m["value"]
        return "", 404
    
@pngoverlayapi.route("/media/file/<name>/bounds", methods=["POST", "DELETE"])
def set_media_file_bounds(name:str):
    mlist = medialist.load_media_list()
    if name not in mlist:
        return "", 404
    m = mlist[name]
    if request.method == "POST":
        bounds = {}
        for k in ["top", "right", "bottom", "left"]:
            if k not in request.form:
                continue
            v_s = request.form[k]
            if v_s.isdigit():
                bounds[k] = int(v_s)
            else:
                return "Bounds must be integers", 422
        if bounds:
            m["bounds"] = bounds
            medialist.save_media_list(mlist)
            return "", 200
        else:
            return "No bounds specified", 422
    else:
        m.pop("bounds", None)
        medialist.save_media_list(mlist)
        return "", 200
        

@pngoverlayapi.get("/state/current")
@serve_when_loaded(web_loaded_callback)
def get_current_state():
    return _get_state_data(nav_stack)

@pngoverlaypages.get("/")
@serve_when_loaded(web_loaded_callback)
def statemap_interface():
    return render_template("states.html")

@pngoverlayoverlays.get("/")
@serve_when_loaded(web_loaded_callback)
def get_overlay():
    return render_template("pngbinds_overlay.html")

@pngoverlaypages.get("/media")
@serve_when_loaded(web_loaded_callback)
def media_interface():
    return render_template("media.html")

def add_routes(app:Flask, api:Blueprint, add_interface=True, add_overlay=True, add_api=True):
    if add_interface:
        add_bp_if_new(pngoverlaypages_parent, pngoverlaypages)
    if add_overlay:
        add_bp_if_new(pngoverlaypages_parent, pngoverlayoverlays)
    if add_overlay or add_interface:
        add_bp_if_new(app, pngoverlaypages_parent)
    if add_api:
        add_bp_if_new(api, pngoverlayapi)

def event_key_press(event:events.Event):
    if event_negotiator is None:
        return
    event_negotiator.last_keybind_trigger = datetime.now(timezone.utc)
    hold_start = event.data.get("hold_start", None)
    if isinstance(hold_start, bool):
        event_negotiator.keybind_holding = hold_start
    event_negotiator.update_event_activity()


def attach_listeners():
    keybinds_keylisteners.add_listener("key_press", event_key_press)

def remove_listeners():
    kp = keybinds_keylisteners.listeners.get("key_press", None)
    if kp is not None:
        i = 0
        while i < len(kp):
            el = kp[i]
            if el.callback is event_key_press:
                del kp[i]
            else:
                i += 1