from . import event_negotiation, medialist, statemapping
import config
from datetime import datetime, timedelta, timezone
import events
from flask import Blueprint, Flask, render_template, request, send_file
from flask_sock import Server
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

web_loaded = False
web_loaded_callback = lambda: web_loaded

meta:plugins.Meta = None
nav_stack:statemapping.NavigatorStackFrame = None
statemap:statemapping.StateMap = None
event_negotiator:event_negotiation.EventNegotiator = None
event_negotiator_thread:threading.Thread = None
keyevents = events.EventBucketContainer()
keylisteners = events.EventListenerCollection()
last_statemap_send = datetime.now()

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
    if os.path.isfile(statemapping.STATEMAP_FILE):
        with open(statemapping.STATEMAP_FILE) as f:
            return statemapping.StateMap.load(f)
    return statemapping.StateMap()

def send_statemap(statemap:statemapping.StateMapNavigator=None):
    global last_statemap_send
    now = datetime.now()
    if (now - last_statemap_send) <= STATEMAP_SEND_COOLDOWN:
        return
    last_statemap_send = now
    if statemap is None:
        statemap = load_statemap()
    keyevents.dispatch(events.Event("statemap_update", {"statemap": statemap.__getstate__()}))

@keylisteners.listener("stack_update")
def event_stack_update(event:events.Event):
    global nav_stack
    frames = event.data["stack"]
    statemap = load_statemap()
    send_statemap(statemap)
    stack:statemapping.NavigatorStackFrame = None
    for statename in reversed(frames):
        state = statemap.states.get(statename, None)
        transitions = statemap.transitions.get(statename, [])
        stack = statemapping.NavigatorStackFrame(state, transitions, stack)
    changed = not (stack is None or nav_stack is None) and stack.state != nav_stack.state
    nav_stack = stack
    if changed:
        if event_negotiator is not None:
            event_negotiator.update_event_activity()
        dispatch_state_change_event()

@keylisteners.listener("key_press")
def event_key_press(event:events.Event):
    if event_negotiator is None:
        return
    event_negotiator.last_keybind_trigger = datetime.now(timezone.utc)
    hold_start = event.data.get("hold_start", None)
    if isinstance(hold_start, bool):
        event_negotiator.keybind_holding = hold_start
    event_negotiator.update_event_activity()

    
pngbindspages_parent = Blueprint("pngbindsparent", __name__, static_folder=STATIC_DIR, static_url_path="/static/pngbinds")
pngbindspages = Blueprint("pngbinds", __name__, url_prefix="/pngbinds", template_folder=TEMPATES_DIR)
pngbindsoverlays = Blueprint("pngbindsoverlay", __name__, url_prefix="/pngbinds/overlay", template_folder=TEMPATES_DIR)
pngbindsapi = Blueprint("pngbindsapi", __name__, url_prefix="/pngbinds")

@pngbindsapi.route("/statemap.json", methods=["GET", "PUT"])
@serve_when_loaded(web_loaded_callback)
def statemap_file():
    if request.method == "PUT":
        statemap = statemapping.StateMap.__new__(statemapping.StateMap)
        try:
            statemap.__setstate__(request.get_json())
        except (KeyError, TypeError, AttributeError) as e:
            traceback.print_exception(e)
            return "", 422
        with open(statemapping.STATEMAP_FILE, "w") as f:
            statemap.dump(f, indent="    ")
        return "", 200
    elif os.path.isfile(statemapping.STATEMAP_FILE):
        return send_file(statemapping.STATEMAP_FILE)
    else:
        return {}

@pngbindsapi.get("/media/list")
@serve_when_loaded(web_loaded_callback)
def get_media_list():
    return medialist.load_media_list()

@pngbindsapi.route("/media/file/<name>", methods=["GET", "POST", "DELETE"])
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
    
@pngbindsapi.route("/media/file/<name>/bounds", methods=["POST", "DELETE"])
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

@sock.route("/events", bp=pngbindsapi)
@serve_when_loaded(web_loaded_callback)
def keybinds_events(ws:Server):
    global statemap

    if keyevents.buckets:
        ws.close(418)
        return #one connection at a time
    bucket = keyevents.new_bucket()

    statemap = load_statemap()
    
    #init event
    ws.send(events.Event("nav_init", {
        "statemap": statemap.__getstate__(),
        "default_state": get_config_default_state(meta)
    }).to_json())

    try:
        while ws.connected:
            msg = ws.receive(0)
            if isinstance(msg, (str, bytes)):
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    print("pngbinds:\tapi /events message invalid json:", msg)
                else:
                    if isinstance(data, dict) and isinstance((event_name := data.get("name", None)), str):
                        event = events.Event(event_name, data.get("data"))
                        keylisteners.handle_event(event)
            for event in bucket.dump():
                ws.send(event.to_json())
    except KeyboardInterrupt:
        pass
    finally:
        if ws.connected:
            ws.close()
        keyevents.remove_bucket(bucket)
        

@pngbindsapi.get("/state/current")
@serve_when_loaded(web_loaded_callback)
def get_current_state():
    return _get_state_data(nav_stack)

@pngbindspages.get("/")
@serve_when_loaded(web_loaded_callback)
def statemap_interface():
    return render_template("states.html")

@pngbindsoverlays.get("/")
@serve_when_loaded(web_loaded_callback)
def get_overlay():
    return render_template("pngbinds_overlay.html")

@pngbindspages.get("/media")
@serve_when_loaded(web_loaded_callback)
def media_interface():
    return render_template("media.html")

def add_routes(app:Flask, api:Blueprint, add_interface=True, add_overlay=True, add_api=True):
    if add_interface:
        add_bp_if_new(pngbindspages_parent, pngbindspages)
    if add_overlay:
        add_bp_if_new(pngbindspages_parent, pngbindsoverlays)
    if add_overlay or add_interface:
        add_bp_if_new(app, pngbindspages_parent)
    if add_api:
        add_bp_if_new(api, pngbindsapi)