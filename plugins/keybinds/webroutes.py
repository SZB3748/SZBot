from . import keybind, keybind_triggers
import asyncio
import events
from flask import Blueprint, Flask, render_template
from flask_sock import Server
import inspect
import json
import os
import plugins
import threading
from uuid import UUID, uuid4
from web import add_bp_if_new, serve_when_loaded, sock

DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(DIR, "static")
TEMPATES_DIR = os.path.join(DIR, "templates")

web_loaded = False
web_loaded_callback = lambda: web_loaded

meta:plugins.Meta = None

keyevents = events.EventBucketContainer()
keylisteners = events.EventListenerCollection()
keys_buckets = events.EventBucketContainer()

_run_trigger = True
_run_trigger_loop = None
_run_triggers_queue:list[keybind_triggers.KeyBindTrigger] = []
_run_triggers_queue_lock = threading.Lock()
_run_triggers_queue_ready = asyncio.Event()

_run_triggers_futures:dict[UUID, asyncio.Future] = {}
_run_triggers_futures_lock = asyncio.Lock()

async def _run_triggers(id, triggers:list[keybind_triggers.KeyBindTrigger]):
    try:
        await asyncio.gather(*(c for kbt in triggers if inspect.isawaitable(c:=kbt.handle())))
    finally:
        async with _run_triggers_futures_lock:
            _run_triggers_futures.pop(id,None)

async def run_triggers_loop():
    _loop = asyncio.get_running_loop()
    while _run_trigger:
        await _run_triggers_queue_ready.wait()
        if not _run_trigger:
            return
        with _run_triggers_queue_lock:
            triggers = _run_triggers_queue.copy()
            _run_triggers_queue.clear()
            _run_triggers_queue_ready.clear()
        uid = uuid4()
        async with _run_triggers_futures_lock:
            _run_triggers_futures[uid] = asyncio.ensure_future(_run_triggers(uid, triggers), loop=_loop)

def run_triggers_thread_handler():
    global _run_trigger_loop
    _run_triggers_queue_ready.clear()
    _run_trigger_loop = loop = asyncio.new_event_loop()
    loop.run_until_complete(run_triggers_loop())

def send_keybinds(merged:dict[str,keybind_triggers.KeyBindTrigger]): #TODO keybinds type and serialization to tuple[str,int]
    binds = set()
    for t in merged.values():
        binds.add((t.kb.keys, t.kb.mode.value))
    keyevents.dispatch(events.Event("update_keybinds", {"binds": list(binds)}))

@keylisteners.listener("key_press")
def event_key_press(event:events.Event):
    keys = event.data["keybind"]
    names = keybind.parse_keybind_string(keys)
    mode = keybind.KeyBindMode(event.data["mode"])
    keys_buckets.dispatch(event)
    print("keybinds: press", keys, mode.name)
    triggers:list[keybind_triggers.KeyBindTrigger] = []
    for kbt in keybind_triggers.merge_keybind_triggers().values():
        if mode != kbt.kb.mode:
            continue
        onames = keybind.parse_keybind_string(kbt.kb.keys)
        if names == onames:
            triggers.append(kbt)
    if triggers:
        with _run_triggers_queue_lock:
            _run_triggers_queue.extend(triggers)
            _run_trigger_loop.call_soon_threadsafe(_run_triggers_queue_ready.set)

@keylisteners.listener("failed_keybinds")
def event_keybind_fail(event:events.Event):
    binds:list[tuple[str,int]] = event.data["binds"]
    print("keybinds: failed to register:")
    for keys, mode in binds:
        print("keybinds:", keys, keybind.KeyBindMode(mode).name if mode in keybind.KeyBindMode else f"unknown ({mode})")

keybindspages_parent = Blueprint("keybindsparent", __name__, static_folder=STATIC_DIR, static_url_path="/static/keybinds")
keybindspages = Blueprint("keybinds", __name__, url_prefix="/keybinds", template_folder=TEMPATES_DIR)
keybindsapi = Blueprint("keybindsapi", __name__, url_prefix="/keybinds")

@sock.route("/events", bp=keybindsapi)
@serve_when_loaded(web_loaded_callback)
def keybinds_events(ws:Server):
    if keyevents.buckets:
        ws.close(418)
        return #one connection at a time
    bucket = keyevents.new_bucket()

    merged = keybind_triggers.merge_keybind_triggers()
    if merged:
        send_keybinds(merged)
    try:
        while ws.connected:
            msg = ws.receive(0.001)
            if isinstance(msg, (str, bytes)):
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    print("keybinds:\tapi /events message invalid json:", msg)
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

@sock.route("/events/keys", bp=keybindsapi)
@serve_when_loaded(web_loaded_callback)
def keybinds_events_keys(ws:Server):
    bucket = keys_buckets.new_bucket()
    try:
        while ws.connected:
            bucket.wait()
            for event in bucket.dump():
                ws.send(event.to_json())
    except KeyboardInterrupt:
        pass
    finally:
        if ws.connected:
            ws.close()
        keys_buckets.remove_bucket(bucket)

@keybindspages.get("/")
@serve_when_loaded(web_loaded_callback)
def statemap_interface():
    return render_template("keybinds.html")


def add_routes(app:Flask, api:Blueprint, add_interface=True, add_api=True):
    if add_interface:
        add_bp_if_new(keybindspages_parent, keybindspages)
        add_bp_if_new(app, keybindspages_parent)
    if add_api:
        add_bp_if_new(api, keybindsapi)