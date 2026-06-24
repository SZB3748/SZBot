from . import keybind, keybind_triggers
import actions
import events
import exiting
from flask import Blueprint, Flask, render_template
from flask_sock import Server
import json
import os
import plugins
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
    triggers:list[tuple[keybind_triggers.KeyBindTrigger, tuple, dict]] = []
    for kbt in keybind_triggers.merge_keybind_triggers().values():
        if mode != kbt.kb.mode:
            continue
        onames = keybind.parse_keybind_string(kbt.kb.keys)
        if names == onames:
            triggers.append((kbt, (), {}))
    if triggers:
        actions.enqueue_triggers(triggers)

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

    @exiting.register_cleanup_listener
    def _cleanup(ctx):
        exiting.unregister_cleanup_listener(_cleanup)
        keyevents.remove_bucket(bucket)
        if ws.connected:
            print(f"closing keybinds events connection {bucket.id}")
            ws.close()
            print(f"closed keybinds events connection {bucket.id}")
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
    finally:
        _cleanup(None)

@sock.route("/events/keys", bp=keybindsapi)
@serve_when_loaded(web_loaded_callback)
def keybinds_events_keys(ws:Server):
    bucket = keys_buckets.new_bucket()
    @exiting.register_cleanup_listener
    def _cleanup(ctx):
        exiting.unregister_cleanup_listener(_cleanup)
        keys_buckets.remove_bucket(bucket)
        if ws.connected:
            print(f"closing keybinds key events connection {bucket.id}")
            ws.close()
            print(f"closed keybinds key events connection {bucket.id}")
    try:
        while ws.connected:
            bucket.wait()
            for event in bucket.dump():
                ws.send(event.to_json())
    finally:
        _cleanup(None)

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