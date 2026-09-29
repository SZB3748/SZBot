from . import medialist, statemapping, webroutes
import events
import logenv
import os
import plugins
import runtime as rt
import threading
from typing import Protocol
import web

DIR = os.path.dirname(__file__)
KEYBOARD_LISTENER_FILE = os.path.join(DIR, "keyboard_listener.py")

COMPONENT_INTERFACE = "interface"
COMPONENT_OVERLAY = "overlay"
COMPONENT_API = "api"
COMPONENT_EVENTS = "events"

P_MICROPHONE = "microphone"
P_KEYBINDS = "keybinds"

init = plugins.PluginInit().bind()

microphone_read_thread:threading.Thread = None
keybinds_key_events_thread:threading.Thread = None

#can be overriden
def create_navigator(statemap:statemapping.StateMap, default_state:str,
                     on_push:statemapping.OnPushCallback, on_pop:statemapping.OnPopCallback, on_change:statemapping.OnChangeCallback):
    return statemapping.StateMapNavigator(statemap, default_state, on_push, on_pop, on_change)

class MicrophoneModule(Protocol):
    COMPONENT_API:str

class KeybindsModule(Protocol):
    class _webroutes_t(Protocol):
        keylisteners:events.EventListenerCollection

    COMPONENT_API:str
    webroutes:_webroutes_t
    

@init.event()
def on_load(ctx:plugins.LoadEvent):
    global microphone_read_thread, keybinds_key_events_thread

    if not os.path.isdir(medialist.MEDIA_DIR):
        os.mkdir(medialist.MEDIA_DIR)

    webroutes.meta = ctx.plugin.meta
    webroutes.web_loaded = True

    m_interface = ctx.plugin.get_component_mode(COMPONENT_INTERFACE)
    m_overlay = ctx.plugin.get_component_mode(COMPONENT_OVERLAY)
    m_api = ctx.plugin.get_component_mode(COMPONENT_API)
    m_events = ctx.plugin.get_component_mode(COMPONENT_EVENTS)

    microphone = plugins.fetch(P_MICROPHONE)
    microphone_m = plugins.fetch_module(microphone, MicrophoneModule)
    keybinds = plugins.fetch(P_KEYBINDS)
    keybinds_m = plugins.fetch_module(keybinds, KeybindsModule)

    if microphone_m is None:
        if microphone is None:
            logenv.main.info("plugin could not be found: {name}", name=P_MICROPHONE, human_text=f"{ctx.plugin.name} plugin tried to access {P_MICROPHONE} plugin but could not (not necessarily a bad thing).")
        else:
            logenv.main.warn("expected plugin to be enabled: {name}", name=P_MICROPHONE, human_text=f"{ctx.plugin.name} plugin found {P_MICROPHONE} plugin and expected it to be enabled, but it is disabled.")
        microphone_m_api = plugins.COMPONENT_MODE_OFF
    else:
        statemapping.EVENT_CONDITION_TYPES[statemapping.MicActivityCondition.CATEGORY_NAME] = statemapping.MicActivityCondition
        microphone_m_api = microphone.get_component_mode(microphone_m.COMPONENT_API)
        if plugins.is_normal(microphone_m_api):
            _args = f"{rt.host_addr[0]}:{rt.host_addr[1]}", web.SELF_SECURE
        elif plugins.is_remote(microphone_m_api):
            raddr, rsecure = plugins.must_have_remote_address(f"Plugin {ctx.plugin.name} requires a remote address to be specified.")
            _args = f"{raddr[0]}:{raddr[1]}", rsecure
        else:
            _args = None
        if _args is not None:
            statemapping.mic_volumes_run = True
            microphone_read_thread = threading.Thread(target=statemapping.mic_volume_background_runner, args=_args)
            microphone_read_thread.start()

    if keybinds_m is None:
        if microphone is None:
            logenv.main.info("plugin could not be found: {name}", name=P_KEYBINDS, human_text=f"{ctx.plugin.name} plugin tried to access {P_KEYBINDS} plugin but could not (not necessarily a bad thing).")
        else:
            logenv.main.warn("expected plugin to be enabled: {name}", name=P_KEYBINDS, human_text=f"{ctx.plugin.name} plugin found {P_KEYBINDS} plugin and expected it to be enabled, but it is disabled.")
        keybinds_m_api = plugins.COMPONENT_MODE_OFF
    else:
        keybinds_m_api = keybinds.get_component_mode(keybinds_m.COMPONENT_API)
        if plugins.is_normal(keybinds_m_api):
            webroutes.keybinds_keylisteners = keybinds_m.webroutes.keylisteners
            webroutes.attach_listeners()
        elif plugins.is_remote(keybinds_m_api):
            webroutes.keybinds_keylisteners = events.EventListenerCollection()
            keybinds_key_events_thread = threading.Thread(target=webroutes.listen_remote_events_keys, args=(rt.remote_addr, rt.remote_secure))
            keybinds_key_events_thread.start()
            webroutes.attach_listeners()

    if ctx.is_start:
        webroutes.add_routes(web.app, web.api, plugins.is_normal(m_interface), plugins.is_normal(m_overlay), plugins.is_normal(m_api))
        rinterface = plugins.is_remote(m_interface)
        roverlay = plugins.is_remote(m_overlay)
        vpngoverlaypages_parent = webroutes.Blueprint("proxy_pngoverlayparent", __name__, static_folder=webroutes.pngoverlaypages_parent.static_folder, template_folder=webroutes.pngoverlaypages_parent.template_folder, static_url_path=webroutes.pngoverlaypages_parent.static_url_path)
        if rinterface:
            web.create_component_proxy(vpngoverlaypages_parent, webroutes.pngoverlaypages.name, webroutes.pngoverlaypages.url_prefix, socket=False)
        if roverlay:
            web.create_component_proxy(vpngoverlaypages_parent, webroutes.pngoverlayoverlays.name, webroutes.pngoverlayoverlays.url_prefix, socket=False)
        if rinterface or roverlay:
            web.add_bp_if_new(web.app, vpngoverlaypages_parent)
        if plugins.is_remote(m_api):
            web.create_component_proxy(web.api, webroutes.pngoverlayapi.name, webroutes.pngoverlayapi.url_prefix)

    if plugins.is_normal(m_api):
        webroutes.init_statemap(ctx.plugin.meta)
        if plugins.is_normal(m_events):
            event_negotiator = webroutes.event_negotiator = statemapping.EventNegotiator(lambda: webroutes.navigator.stack, lambda: webroutes.navigator.statemap, webroutes.dispatch_state_change_event)
            webroutes.event_negotiator_thread = threading.Thread(target=event_negotiator.background_task)
            webroutes.event_negotiator_thread.start()
    elif plugins.is_normal(m_events):
        logenv.main.warn(f"{ctx.plugin.name} event negotiator will not be run due to api component mode: {{mode}}", mode=m_api)

@init.event()
def on_unload(ctx:plugins.UnloadEvent):
    global microphone_read_thread, keybinds_key_events_thread
    webroutes.web_loaded = False
    if webroutes.keybinds_keylisteners is not None:
        webroutes.remove_listeners()
        webroutes.keybinds_keylisteners = None
    if statemapping.mic_volumes_run:
        statemapping.mic_volumes_run = False
        if statemapping._mic_volumes_proc is not None:
            statemapping._mic_volumes_proc.stdout.close()
        microphone_read_thread.join(0.5)
    # if keyboard_listener_proc is not None: #TODO get this from keybinds plugin
    #     webroutes.nav_stack = None
    #     webroutes.dispatch_state_change_event()
    if keybinds_key_events_thread is not None:
        if webroutes.remote_event_keys_websocket is not None:
            webroutes.remote_event_keys_websocket.close()
            keybinds_key_events_thread.join(0.5)
        keybinds_key_events_thread = None
    if webroutes.event_negotiator:
        webroutes.event_negotiator_thread.join(0.5)
        webroutes.event_negotiator_thread = None
