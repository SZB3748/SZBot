from . import keybind_triggers, webroutes
import exiting
import logenv
import os
import plugins
import runtime as rt
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

def keyboard_listener_cleanup(ctx):
    global keyboard_listener_proc
    exiting.unregister_cleanup_listener(keyboard_listener_cleanup)
    if keyboard_listener_proc is None or keyboard_listener_proc.poll() is None:
        logenv.main.info("keyboard key listener process has already ended")
        keyboard_listener_proc = None
    else:
        logenv.main.info("ending keyboard key listener process")
        keyboard_listener_proc.kill()
        keyboard_listener_proc = None
        logenv.main.info("ended keyboard key listener process")


def run_keyboard_listener(api_host_address:tuple[str,int], secure_api:bool=False):
    exiting.register_cleanup_listener(keyboard_listener_cleanup)
    return subprocess.Popen([sys.executable, KEYBOARD_LISTENER_FILE, f"ws{"s"*secure_api}://{api_host_address[0]}:{api_host_address[1]}/api/keybinds/events"])

def on_load(ctx:plugins.LoadEvent):
    global keyboard_listener_proc

    webroutes.meta = ctx.plugin.meta
    webroutes.web_loaded = True

    m_interface = ctx.plugin.get_component_mode(COMPONENT_INTERFACE)
    m_api = ctx.plugin.get_component_mode(COMPONENT_API)
    m_listener = ctx.plugin.get_component_mode(COMPONENT_LISTENER)

    keybind_triggers.ActionKeyBindTrigger.enabled(True)

    if ctx.is_start:
        webroutes.add_routes(web.app, web.api, m_interface == plugins.COMPONENT_MODE_NORMAL, m_api == plugins.COMPONENT_MODE_NORMAL)
        rinterface = m_interface == plugins.COMPONENT_MODE_REMOTE
        rapi = m_api == plugins.COMPONENT_MODE_REMOTE
        if rinterface or rapi:
            plugins.must_have_remote_address(f"The {ctx.plugin.name} plugin requires a remote address to be specified.")
        vpngoverlaypages_parent = webroutes.Blueprint("proxy_keybindsparent", __name__, static_folder=webroutes.keybindspages_parent.static_folder, template_folder=webroutes.keybindspages_parent.template_folder, static_url_path=webroutes.keybindspages_parent.static_url_path)
        if rinterface:
            web.create_component_proxy(vpngoverlaypages_parent, webroutes.keybindspages.name, webroutes.keybindspages.url_prefix, socket=False)
            web.add_bp_if_new(web.app, vpngoverlaypages_parent)
        if rapi:
            web.create_component_proxy(web.api, webroutes.keybindsapi.name, webroutes.keybindsapi.url_prefix)

    if m_listener == plugins.COMPONENT_MODE_NORMAL:
        keyboard_listener_proc = run_keyboard_listener(rt.host_addr, web.SELF_SECURE)
    elif m_listener == plugins.COMPONENT_MODE_REMOTE:
        remote_address, remote_secure = plugins.must_have_remote_address(f"The {ctx.plugin.name} plugin requires a remote address to be specified.")
        keyboard_listener_proc = run_keyboard_listener(remote_address, remote_secure)

def on_unload(ctx:plugins.UnloadEvent):
    webroutes.web_loaded = False
    keybind_triggers.ActionKeyBindTrigger.enabled(False)
    keyboard_listener_cleanup(None)


cleanup = lambda _: on_unload