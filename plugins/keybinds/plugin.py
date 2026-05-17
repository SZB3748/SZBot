from . import webroutes
import events
import os
import plugins
import subprocess
import sys
import web

DIR = os.path.dirname(__file__)
KEYBOARD_LISTENER_FILE = os.path.join(DIR, "keyboard_listener.py")

COMPONENT_INTERFACE = "interface"
COMPONENT_API = "api"
COMPONENT_LISTENER = "listener"

keyboard_listener_proc:subprocess.Popen = None

#TODO allow for trigger to listen for a set of keybinds (one of any) or any keybinds; have the keybind mappable into the requested values

def run_keyboard_listener(api_host_address:str, secure_api:bool=False):
    s = "s" * secure_api
    return subprocess.Popen([sys.executable, KEYBOARD_LISTENER_FILE, f"ws{s}://{api_host_address}/api/keybinds/events"])

def on_load(ctx:plugins.LoadEvent):
    global keyboard_listener_proc

    webroutes.meta = ctx.plugin.meta
    webroutes.web_loaded = True

    m_interface = ctx.plugin.get_component_mode(COMPONENT_INTERFACE)
    m_api = ctx.plugin.get_component_mode(COMPONENT_API)
    m_listener = ctx.plugin.get_component_mode(COMPONENT_LISTENER)

    if ctx.is_start:
        webroutes.add_routes(web.app, web.api, m_interface == plugins.COMPONENT_MODE_NORMAL, m_api == plugins.COMPONENT_MODE_NORMAL)
        rinterface = m_interface == plugins.COMPONENT_MODE_REMOTE
        vpngoverlaypages_parent = webroutes.Blueprint("proxy_keybindsparent", __name__, static_folder=webroutes.keybindspages_parent.static_folder, template_folder=webroutes.keybindspages_parent.template_folder, static_url_path=webroutes.keybindspages_parent.static_url_path)
        if rinterface:
            web.create_component_proxy(ctx.remote_api_addr, vpngoverlaypages_parent, webroutes.keybindspages.name, webroutes.keybindspages.url_prefix, socket=False)
            web.add_bp_if_new(web.app, vpngoverlaypages_parent)
        if m_api == plugins.COMPONENT_MODE_REMOTE:
            web.create_component_proxy(ctx.remote_api_addr, web.api, webroutes.keybindsapi.name, webroutes.keybindsapi.url_prefix)

    if m_listener == plugins.COMPONENT_MODE_NORMAL:
        keyboard_listener_proc = run_keyboard_listener(f"{ctx.host_addr[0]}:{ctx.host_addr[1]}", ctx.host_addr[1] == 443)
    elif m_listener == plugins.COMPONENT_MODE_REMOTE:
        assert ctx.remote_api_addr is not None, "Cannot start key listener in remote mode, missing remote API address."
        keyboard_listener_proc = run_keyboard_listener(ctx.remote_api_addr, ctx.remote_api_addr.endswith(":443"))

def on_unload(ctx:plugins.UnloadEvent):
    global keyboard_listener_proc
    webroutes.web_loaded = False
    if keyboard_listener_proc is not None:
        webroutes.keyevents.dispatch(events.Event("cleanup"))
        keyboard_listener_proc.terminate()
        keyboard_listener_proc = None
