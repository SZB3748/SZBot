from . import webroutes
import config
import plugins
import threading
import web

COMPONENT_INTERFACE = "interface"
COMPONENT_API = "api"
COMPONENT_HANDLER = "handler"

handler_thread:threading.Thread = None

def on_load(ctx:plugins.LoadEvent):
    global handler_thread

    #handler._meta = ctx.plugin.meta
    webroutes.web_loaded = True

    m_interface = ctx.plugin.get_component_mode(COMPONENT_INTERFACE)
    m_api = ctx.plugin.get_component_mode(COMPONENT_API)
    m_handler = ctx.plugin.get_component_mode(COMPONENT_HANDLER)

    if ctx.is_start:
        webroutes.add_routes(web.app, web.api, m_interface == plugins.COMPONENT_MODE_NORMAL, m_api == plugins.COMPONENT_MODE_NORMAL)
        rinterface = m_interface == plugins.COMPONENT_MODE_REMOTE
        vmicrophonepages_parent = webroutes.Blueprint("proxy_microphoneparent", __name__, static_folder=webroutes.microphone_parent.static_folder, template_folder=webroutes.microphone_parent.template_folder, static_url_path=webroutes.microphone_parent.static_url_path)
        if rinterface:
            web.create_component_proxy(ctx.remote_api_addr, vmicrophonepages_parent, webroutes.microphonepages.name, webroutes.microphonepages.url_prefix, socket=False)
            web.add_bp_if_new(web.app, vmicrophonepages_parent)
        if m_api == plugins.COMPONENT_MODE_REMOTE:
            web.create_component_proxy(ctx.remote_api_addr, web.api, webroutes.microphoneapi.name, webroutes.microphoneapi.url_prefix)
    
    assert m_handler != plugins.COMPONENT_MODE_REMOTE, "Microphone handler has no remote mode."
    if m_handler == plugins.COMPONENT_MODE_NORMAL:
        c_parent:dict[str] = plugins.read_configs(config.CONFIG_FILE, ctx.plugin.meta)
        c = c_parent.get("Microphone", None)
        devices = None
        if isinstance(c, dict):
            devices = c.get("Devices", None)
        
        if isinstance(devices, list):
            webroutes.main_handler.from_init(devices)
            handler_thread = threading.Thread(target=webroutes.main_handler.handle, daemon=True)
            handler_thread.start()
        else:
            print("Microphone: could not find initialization info from configs.")

def on_unload(ctx:plugins.UnloadEvent):
    global handler_thread
    webroutes.web_loaded = False
    if handler_thread:
        old = handler_thread
        handler_thread = None
        webroutes.main_handler.do_handle = False
        print("Waiting for microphone handler to stop...")
        old.join(0.5)
        if old.is_alive():
            print("Microphone handler failed to stop after 0.5 seconds")
        else:
            print("Microphone handler stopped")