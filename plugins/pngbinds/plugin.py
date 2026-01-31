from . import medialist, statemapping, webroutes
import events
import os
import plugins
import threading
import subprocess
import sys
import web

DIR = os.path.dirname(__file__)
KEYBOARD_LISTENER_FILE = os.path.join(DIR, "keyboard_listener.py")

COMPONENT_INTERFACE = "interface"
COMPONENT_OVERLAY = "overlay"
COMPONENT_API = "api"
COMPONENT_LISTENER = "listener"
COMPONENT_EVENTS = "events"
#COMPONENT_TWITCHBOT_COMMANDS = "twitchbot:commands"

keyboard_listener_proc:subprocess.Popen = None
microphone_read_thread:threading.Thread = None

def run_keyboard_listener(api_host_address:str, secure_api:bool=False):
    s = "s" * secure_api
    return subprocess.Popen([sys.executable, KEYBOARD_LISTENER_FILE, f"ws{s}://{api_host_address}/api/pngbinds/events"])

#can be overriden
def create_navigator(statemap:statemapping.StateMap, default_state:str,
                     on_push:statemapping.OnPushCallback, on_pop:statemapping.OnPopCallback, on_change:statemapping.OnChangeCallback):
    return statemapping.StateMapNavigator(statemap, default_state, on_push, on_pop, on_change)

def on_load(ctx:plugins.LoadEvent):
    global keyboard_listener_proc, microphone_read_thread

    if not os.path.isdir(medialist.MEDIA_DIR):
        os.mkdir(medialist.MEDIA_DIR)

    webroutes.meta = ctx.plugin.meta
    webroutes.web_loaded = True

    m_interface = ctx.plugin.get_component_mode(COMPONENT_INTERFACE)
    m_overlay = ctx.plugin.get_component_mode(COMPONENT_OVERLAY)
    m_api = ctx.plugin.get_component_mode(COMPONENT_API)
    m_listener = ctx.plugin.get_component_mode(COMPONENT_LISTENER)
    m_events = ctx.plugin.get_component_mode(COMPONENT_EVENTS)

    microphone = ctx.plugin_list.get("microphone", None)
    if microphone is not None and microphone.module is not None:
        statemapping.EVENT_CONDITION_TYPES[statemapping.MicActivityCondition.CATEGORY_NAME] = statemapping.MicActivityCondition
        microphone_m_api = microphone.get_component_mode(microphone.module.COMPONENT_API)
        if microphone_m_api == plugins.COMPONENT_MODE_NORMAL:
            _args = f"{ctx.host_addr[0]}:{ctx.host_addr[1]}", ctx.host_addr[1] == 443
        elif microphone_m_api == plugins.COMPONENT_MODE_REMOTE:
            _args = ctx.remote_api_addr, ctx.remote_api_addr.endswith(":443")
        else:
            _args = None
        if _args is not None:
            statemapping.mic_volumes_run = True
            microphone_read_thread = threading.Thread(target=statemapping.mic_volume_background_runner, args=_args, daemon=True)
            microphone_read_thread.start()


    if ctx.is_start:
        webroutes.add_routes(web.app, web.api, m_interface == plugins.COMPONENT_MODE_NORMAL, m_overlay == plugins.COMPONENT_MODE_NORMAL, m_api == plugins.COMPONENT_MODE_NORMAL)
        rinterface = m_interface == plugins.COMPONENT_MODE_REMOTE
        roverlay = m_overlay == plugins.COMPONENT_MODE_REMOTE
        vpngbindspages_parent = webroutes.Blueprint("proxy_pngbindsparent", __name__, static_folder=webroutes.pngbindspages_parent.static_folder, template_folder=webroutes.pngbindspages_parent.template_folder, static_url_path=webroutes.pngbindspages_parent.static_url_path)
        if rinterface:
            web.create_component_proxy(ctx.remote_api_addr, vpngbindspages_parent, webroutes.pngbindspages.name, webroutes.pngbindspages.url_prefix, socket=False)
        if roverlay:
            web.create_component_proxy(ctx.remote_api_addr, vpngbindspages_parent, webroutes.pngbindsoverlays.name, webroutes.pngbindsoverlays.url_prefix, socket=False)
        if rinterface or roverlay:
            web.add_bp_if_new(web.app, vpngbindspages_parent)
        if m_api == plugins.COMPONENT_MODE_REMOTE:
            web.create_component_proxy(ctx.remote_api_addr, web.api, webroutes.pngbindsapi.name, webroutes.pngbindsapi.url_prefix)
    
    assert m_events != plugins.COMPONENT_MODE_REMOTE, "PNG Binds event negotiator has no remote mode."
    if m_events == plugins.COMPONENT_MODE_NORMAL:
        event_negotiator = webroutes.event_negotiator = statemapping.EventNegotiator(lambda: webroutes.nav_stack, lambda: webroutes.statemap, webroutes.dispatch_state_change_event)
        webroutes.event_negotiator_thread = threading.Thread(target=event_negotiator.background_task)
        webroutes.event_negotiator_thread.start()

    if m_listener == plugins.COMPONENT_MODE_NORMAL:
        keyboard_listener_proc = run_keyboard_listener(f"{ctx.host_addr[0]}:{ctx.host_addr[1]}", ctx.host_addr[1] == 443)
    elif m_listener == plugins.COMPONENT_MODE_REMOTE:
        assert ctx.remote_api_addr is not None, "Cannot start key listener in remote mode, missing remote API address."
        keyboard_listener_proc = run_keyboard_listener(ctx.remote_api_addr, ctx.remote_api_addr.endswith(":443"))

def on_unload(ctx:plugins.UnloadEvent):
    global microphone_read_thread
    webroutes.web_loaded = False
    if statemapping.mic_volumes_run:
        statemapping.mic_volumes_run = False
        if statemapping._mic_volumes_proc is not None:
            statemapping._mic_volumes_proc.stdout.close()
        microphone_read_thread.join(0.5)
    if keyboard_listener_proc is not None:
        webroutes.nav_stack = None
        webroutes.keyevents.dispatch(events.Event("cleanup"))
        webroutes.dispatch_state_change_event()
        keyboard_listener_proc.terminate()
    if webroutes.event_negotiator:
        webroutes.event_negotiator_thread.join(0.5)
