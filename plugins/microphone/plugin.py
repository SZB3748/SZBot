from . import webroutes
import config
import logenv
import plugins
import threading
import web

COMPONENT_INTERFACE = "interface"
COMPONENT_API = "api"
COMPONENT_HANDLER = "handler"

init = plugins.PluginInit().bind()

handler_thread:threading.Thread = None

@init.event()
def on_load(ctx:plugins.LoadEvent):
    global handler_thread
    webroutes.web_loaded = True

    m_interface = ctx.plugin.get_component_mode(COMPONENT_INTERFACE)
    m_api = ctx.plugin.get_component_mode(COMPONENT_API)
    m_handler = ctx.plugin.get_component_mode(COMPONENT_HANDLER)

    if ctx.is_start:
        webroutes.add_routes(web.app, web.api, plugins.is_normal(m_interface), plugins.is_normal(m_api))
        vmicrophonepages_parent = webroutes.Blueprint("proxy_microphoneparent", __name__, static_folder=webroutes.microphone_parent.static_folder, template_folder=webroutes.microphone_parent.template_folder, static_url_path=webroutes.microphone_parent.static_url_path)
        if plugins.is_remote(m_interface):
            web.create_component_proxy(vmicrophonepages_parent, webroutes.microphonepages.name, webroutes.microphonepages.url_prefix, socket=False)
            web.add_bp_if_new(web.app, vmicrophonepages_parent)
        if plugins.is_remote(m_api):
            web.create_component_proxy(web.api, webroutes.microphoneapi.name, webroutes.microphoneapi.url_prefix)
    
    if plugins.is_normal(m_handler):
        c_parent:dict[str] = plugins.read_configs(config.CONFIG_FILE, ctx.plugin.meta)
        c = c_parent.get("Microphone", None)
        devices = None
        if isinstance(c, dict):
            devices = c.get("Devices", None)
        
        if isinstance(devices, list):
            webroutes.main_handler.from_init(devices)
            handler_thread = threading.Thread(target=webroutes.main_handler.handle)
            handler_thread.start()
        else:
            logenv.main.error("Microphone: could not find initialization info from configs.")

@init.event()
def on_unload(ctx:plugins.UnloadEvent):
    global handler_thread
    webroutes.web_loaded = False
    if handler_thread:
        webroutes.main_handler.stop()
        handler_thread = None