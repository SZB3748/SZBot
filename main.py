import gevent
from gevent import monkey

monkey.patch_all() #must be called first
gevent.get_hub().NOT_ERROR += (KeyboardInterrupt,)

import asyncio
import asyncio_gevent
asyncio.set_event_loop_policy(asyncio_gevent.EventLoopPolicy())

import actions
import argparse
import atexit
import config
import exiting
import os
import plugins
import runtime as rt
import signal
import threading
import traceback
import web

parser = argparse.ArgumentParser(description="SZBot main program.")
parser.add_argument("-d", "--addr", default=f"{web.HOST}:{web.PORT}", help="Address to host the flask app on. Can be `host:port`, `host`, or `port`.")
parser.add_argument("--remote-addr", default=None, help="The IP/Domain:Port to connect to for any remote behavior. May be required to run depending on plugins. Must be supplied as `[protocol://]host:port`.")
parser.add_argument("--remote-secure", default="auto", choices=["yes", "no", "auto"], help="If the bot should make secure connections (https) when connecting to the specified remote. If auto, the remote-addr argument will check for http or https and decide accordingly.")
parser.add_argument("-p", "--plugin-configs", default=config.PLUGIN_FILE, help="Path to the plugin config file to use.")
parser.add_argument("-c", "--configs", default=config.CONFIG_FILE, help="Path to the config file to use.")
parser.add_argument("-C", "--core-component", action="append", default=[], help="Set modes for core components with <name>=<mode> syntax. These modes can be normal|remote|off")

def get_args()->tuple[tuple[str, int], tuple[str,int]|tuple[None,None], bool, str, str, dict[str, str|None]]:
    args = parser.parse_args()
    addr_arg:str = args.addr
    remote_arg:str = args.remote_addr
    secure:str = args.remote_secure

    if ":" in addr_arg:
        host, port = addr_arg.split(":", 1)
        host = host.strip().lower()
        # using localhost can cause significant slowdowns for the
        # API proxy on Windows. cite: https://stackoverflow.com/a/75425128
        if host == "localhost":
            host = "127.0.0.1"
        if host and port:
            if port.isdecimal():
                addr = host, int(port)
            else:
                print("Address port must be an integer.")
                exit(-1)
        elif port and not port.isdecimal():
            print("Address port must be an integer.")
            exit(-1)
        else:
            addr = host or web.HOST, int(port) if port else web.PORT
    elif addr_arg.isdecimal():
        addr = web.HOST, int(addr_arg)
    else:
        host = addr_arg.strip().lower()
        addr = "127.0.0.1" if host == "localhost" else host, web.PORT
    
    if remote_arg is None:
        remote_addr = rt.NO_REMOTE_ADDRESS
        remote_secure = False
    else:
        dds = remote_arg.find("://")
        slash = remote_arg.find("/")
        if dds > -1 and dds < slash:
            protocol, raddr_raw = remote_arg.split("://", 1)
        else:
            protocol = ""
            raddr_raw = remote_arg

        if secure == "yes":
            remote_secure = True
        elif secure == "no":
            remote_secure = False
        elif secure == "auto":
            remote_secure = bool(protocol and protocol.lower() in ("https", "sftp", "wss"))
        else:
            assert False, f"unexpected value for remote-secure: {repr(remote_secure)}"
        
        if slash > -1:
            raddr = raddr_raw.split("/", 1)[0]
        else:
            raddr = raddr_raw
        
        if ":" not in raddr:
            print("Remote address must be formatted `host:port` where `host` can be either an IP or domain and `port` must be an integer.")
            exit(-1)
        host, port = raddr.split(":", 1)

        if host.lower() == "localhost":
            host = "127.0.0.1"
        if not (host and port):
            print("Both remote address host and port are needed where `host` can be either an IP or domain and `port` must be an integer.")
            exit(-1)
        elif not port.isdecimal():
            print("Remote address port must be an integer.")
            exit(-1)
        
        remote_addr = host, int(port)

    expressions:list[str] = args.core_component
    components = {}
    for expr in expressions:
        if "=" in expr:
            name, modename = expr.split("=", 1)
            name = name.strip()
            modename = modename.strip().lower()
            if modename == "off":
                modename = None
            components[name] = modename
        else:
            print("Core component must be in the <name>=<mode> format, got:", expr)
            exit(-1)
    
    return addr, remote_addr, remote_secure, args.configs, args.plugin_configs, components

trigger_runner_thread:threading.Thread|None = None

def exit_handler(e:Exception|None=None):
    atexit.unregister(exit_handler)

    exiting.cleanup(exiting.ExitContext())

    print("unloading enabled plugins")
    for plugin_name in reversed(rt.plugin_load_order):
        plugin = rt.plugin_list[plugin_name]
        if plugin.module is not None:
            plugin.unload(plugins.UnloadEvent(plugin, True, e))
    print("unloaded plugins")

    if trigger_runner_thread is not None:
        actions.stop_trigger_loop()

def run():
    global trigger_runner_thread

    print("reading plugin list")
    rt.plugin_list = plugins.read_plugin_data(path=config.PLUGIN_FILE)
    plugin_enabled_count = sum(1 for plugin in rt.plugin_list.values() if plugin.module is not None and plugin.startup_load)
    print("read", len(rt.plugin_list), "plugins with", plugin_enabled_count, f"enabled plugin{"s" * (not plugin_enabled_count)}")
    print("generating plugin load order")
    rt.plugin_load_order = plugins.generate_load_order(rt.plugin_list)
    if rt.plugin_load_order:
        print("loading enabled plugins")
        for plugin_name in rt.plugin_load_order:
            plugin = rt.plugin_list[plugin_name]
            if plugin.module is not None and plugin.startup_load:
                plugin.load(plugins.LoadEvent(plugin, True))
        print("loaded plugins")
    else:
        print("no plugins made it into the load order\nmake sure that any dependenant plugins are enabled")
    
    print("bot must be started manually")

    if rt.core_components:
        core_meta = plugins.parse_plugin_meta(plugins.CORE_CONFIGS_META)
        invalid_components = plugins.get_invalid_plugin_components(rt.core_components, core_meta)
        if invalid_components:
            raise plugins.InvalidComponentError(f"Component(s) have invalid modes: {", ".join(invalid_components)}")
        
        interface_mode = rt.core_components.get(plugins.CORE_COMPONENT_INTERFACE, plugins.COMPONENT_MODE_NORMAL)
        overlay_mode = rt.core_components.get(plugins.CORE_COMPONENT_OVERLAY, plugins.COMPONENT_MODE_NORMAL)
        api_mode = rt.core_components.get(plugins.CORE_COMPONENT_API, plugins.COMPONENT_MODE_NORMAL)
        tronix_mode = rt.core_components.get(plugins.CORE_COMPONENT_TRONIX, plugins.COMPONENT_MODE_NORMAL)
    else:
        interface_mode = overlay_mode = api_mode = tronix_mode = plugins.COMPONENT_MODE_NORMAL

    
    if api_mode == plugins.COMPONENT_MODE_REMOTE and rt.remote_addr == rt.NO_REMOTE_ADDRESS:
        print("Remote address needed to use core API in remote mode.")
        exit(-1)

    if tronix_mode == plugins.COMPONENT_MODE_NORMAL:
        print("loading script environment")
        import tronix_integrations
        tronix_integrations.activate()
        print("loaded script environment")
        trigger_runner_thread = threading.Thread(target=actions.run_triggers_thread_handler)
    elif tronix_mode == plugins.COMPONENT_MODE_REMOTE:
        print("setting up proxy script environment")
        actions.script_runner = web.ProxyScriptRunner()
        print("set up proxy script environment")
        trigger_runner_thread = threading.Thread(target=actions.run_triggers_thread_handler)
    else:
        trigger_runner_thread = None

    if trigger_runner_thread is not None:
        print("starting trigger runner thread")
        trigger_runner_thread.start()

    web.attach_core(interface_mode, overlay_mode, api_mode, tronix_mode)

    def sigexit(sig, frame):
        print(f"Received signal {sig}, closing...")
        try:
            exiting.cleanup(exiting.ExitContext(sig, frame))
        finally:
            exiting.clear()
            exit(0)

    atexit.register(exit_handler)
    signal.signal(signal.SIGINT, sigexit)
    signal.signal(signal.SIGBREAK, sigexit)

    print("starting web server")
    e = None
    try:
        web.serve()
    except KeyboardInterrupt:
        pass
    except Exception as _e:
        traceback.print_exception(_e)
        e = _e
    
    exit_handler(e)

if __name__ == "__main__":
    actions.current_environment_name = actions.generate_environment_name("main")
    oauth = config.read(path=config.OAUTH_TWITCH_FILE)
    addr, remote_addr, remote_secure, config_path, pconfig_path, core_components = get_args()
    rt.host_addr = addr
    rt.remote_addr = remote_addr
    rt.remote_secure = remote_secure
    rt.core_components = core_components
    if config_path != config.CONFIG_FILE:
        config.CONFIG_FILE = os.path.abspath(config_path)
    if pconfig_path != config.PLUGIN_FILE:
        config.PLUGIN_FILE = os.path.abspath(pconfig_path)
    shared_loop_thread, shared_loop_ready = actions.run_shared_loop()
    shared_loop_ready.wait()
    run()