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

def run_keyboard_listener():
    return subprocess.Popen([sys.executable, KEYBOARD_LISTENER_FILE, "ws://localhost:6742/api/pngbinds/events"])

#can be overriden
def create_navigator(statemap:statemapping.StateMap, default_state:str,
                     on_push:statemapping.OnPushCallback, on_pop:statemapping.OnPopCallback, on_change:statemapping.OnChangeCallback):
    return statemapping.StateMapNavigator(statemap, default_state, on_push, on_pop, on_change)

def on_load(ctx:plugins.LoadEvent):
    global keyboard_listener_proc

    _, plugin, _, *_ = ctx

    if not os.path.isdir(medialist.MEDIA_DIR):
        os.mkdir(medialist.MEDIA_DIR)

    webroutes.meta = plugin.meta
    webroutes.web_loaded = True

    keyboard_listener_proc = run_keyboard_listener()

def on_unload(ctx:plugins.UnloadEvent):
    webroutes.keyevents.dispatch(events.Event("cleanup"))
    webroutes.nav_stack = None
    webroutes.dispatch_state_change_event()
    webroutes.web_loaded = False
    keyboard_listener_proc.terminate()


webroutes.add_routes(web.app, web.api)
