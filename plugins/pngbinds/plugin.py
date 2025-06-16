from . import medialist, statemapping, webroutes
import events
import os
import plugins
import signal
import subprocess
import sys
import web

DIR = os.path.dirname(__file__)
KEYBOARD_LISTENER_FILE = os.path.join(DIR, "keyboard_listener.py")

keyboard_listener_proc:subprocess.Popen = None

def run_keyboard_listener(api_host_address:str, secure_api:bool=False):
    s = "s" * secure_api
    return subprocess.Popen([sys.executable, KEYBOARD_LISTENER_FILE, f"ws{s}://{api_host_address}/api/pngbinds/events"])

#can be overriden
def create_navigator(statemap:statemapping.StateMap, default_state:str,
                     on_push:statemapping.OnPushCallback, on_pop:statemapping.OnPopCallback, on_change:statemapping.OnChangeCallback):
    return statemapping.StateMapNavigator(statemap, default_state, on_push, on_pop, on_change)

def on_load(ctx:plugins.LoadEvent):
    global keyboard_listener_proc

    _, plugin, _, host_addr, remote_api, api_only, *_ = ctx

    if not os.path.isdir(medialist.MEDIA_DIR):
        os.mkdir(medialist.MEDIA_DIR)

    webroutes.meta = plugin.meta
    webroutes.web_loaded = True

    if not api_only:
        keyboard_listener_proc = run_keyboard_listener(f"{host_addr[0]}:{host_addr[1]}", host_addr[1] == 443)

def on_unload(ctx:plugins.UnloadEvent):
    webroutes.web_loaded = False
    if keyboard_listener_proc is not None:
        webroutes.nav_stack = None
        webroutes.keyevents.dispatch(events.Event("cleanup"))
        webroutes.dispatch_state_change_event()
        keyboard_listener_proc.terminate()


webroutes.add_routes(web.app, web.api)
