from gevent import monkey

monkey.patch_all() #must be called first

import actions
import argparse
import config
import os
import plugins
import traceback
import twitch_reauth
import web

parser = argparse.ArgumentParser(description="SZBot main program.")
parser.add_argument("-d", "--addr", default=f"{web.HOST}:{web.PORT}", help="Address to host the flask app on. Can be `host:port`, `host`, or `port`.")
parser.add_argument("--remote-api", default=None, help="The IP/Domain:Port to connect to for any remote behavior. May be required to run depending on plugins.")
parser.add_argument("-p", "--plugin-configs", default=config.PLUGIN_FILE, help="Path to the plugin config file to use.")
parser.add_argument("-c", "--configs", default=config.CONFIG_FILE, help="Path to the config file to use.")
parser.add_argument("-C", "--core-component", action="append", default=[], help="Set modes for core components with <name>=<mode> syntax. These modes can be normal|remote|off")

def get_args()->tuple[tuple[str, int], str|None, str, dict[str, str|None]]:
    args = parser.parse_args()
    addr_arg:str = args.addr
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
                print("Address port must be an integer")
                exit(-1)
        elif port and not port.isdecimal():
            print("Address port must be an integer")
            exit(-1)
        else:
            addr = host or web.HOST, int(port) if port else web.PORT
    elif addr_arg.isdecimal():
        addr = web.HOST, int(addr_arg)
    else:
        host = addr_arg.strip().lower()
        addr = "127.0.0.1" if host == "localhost" else host, web.PORT

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
    
    return addr, args.remote_api, args.configs, args.plugin_configs, components

def run(addr:tuple[str, int]=(web.HOST, web.PORT), remote_api_addr:str=None, pconfig_path:str=config.PLUGIN_FILE, core_components:dict[str, str|None]={}):
    print("reading plugin list")
    plugin_list = plugins.read_plugin_data(path=pconfig_path)
    plugin_enabled_count = sum(1 for plugin in plugin_list.values() if plugin.module is not None and plugin.startup_load)
    print("read", len(plugin_list), "plugins with", plugin_enabled_count, f"enabled plugin{"s" * (not plugin_enabled_count)}")
    print("generating plugin load order")
    load_order = plugins.generate_load_order(plugin_list)
    if load_order:
        print("loading enabled plugins")
        for plugin_name in load_order:
            plugin = plugin_list[plugin_name]
            if plugin.module is not None and plugin.startup_load:
                plugin.load(plugins.LoadEvent(plugin_list, plugin, pconfig_path, True, addr, remote_api_addr))
        print("loaded plugins")
    else:
        print("no plugins made it into the load order\nmake sure that any dependenant plugins are enabled")
    plugins.shared_plugins_list = plugin_list
    print("bot must be started manually")

    if core_components:
        core_meta = plugins.parse_plugin_meta(plugins.CORE_CONFIGS_META)
        invalid_components = plugins.get_invalid_plugin_components(core_components, core_meta)
        if invalid_components:
            raise plugins.InvalidComponentError(f"Component(s) have invalid modes: {", ".join(invalid_components)}")
        
        interface_mode = core_components.get(plugins.CORE_COMPONENT_INTERFACE, plugins.COMPONENT_MODE_NORMAL)
        api_mode = core_components.get(plugins.CORE_COMPONENT_API, plugins.COMPONENT_MODE_NORMAL)
        tronix_mode = core_components.get(plugins.CORE_COMPONENT_TRONIX, plugins.COMPONENT_MODE_NORMAL)
    else:
        interface_mode = api_mode = tronix_mode = plugins.COMPONENT_MODE_NORMAL

    if tronix_mode == plugins.COMPONENT_MODE_NORMAL:
        print("loading script environment")
        import tronix.script_builtins, tronix_integrations
        tronix.script_builtins.activate()
        tronix_integrations.activate(api_mode, *web.process_remote_api(remote_api_addr))
        print("loaded script environment")
    elif tronix_mode == plugins.COMPONENT_MODE_REMOTE:
        print("setting up proxy script environment")
        import actions
        actions.script_runner = web.ProxyScriptRunner(*web.process_remote_api(remote_api_addr))
        print("set up proxy script environment")
        

    web.attach_core(interface_mode, api_mode, tronix_mode, remote_api_addr)

    print("starting web server")
    e = None
    try:
        web.serve(host=addr[0], port=addr[1], pconfig_path=pconfig_path)
    except KeyboardInterrupt:
        pass
    except Exception as _e:
        traceback.print_exception(_e)
        e = _e
    
    print("unloading enabled plugins")
    for plugin in plugin_list.values():
        if plugin.module is not None:
            plugin.unload(plugins.UnloadEvent(plugin_list, plugin, True, e))
    print("unloaded plugins")

if __name__ == "__main__":
    actions.current_environment_name = actions.generate_environment_name("main")
    oauth = config.read(path=config.OAUTH_TWITCH_FILE)
    identity = oauth.get("identity", None)
    if not (isinstance(identity, dict) and "Client-Id" in identity and "Client-Secret" in identity):
        print("You must create an oauth_twitch.json file with your twitch application's Client-Id and Client-Secret.")
    elif "Token" not in identity:
        try:
            addr, *_ = get_args()
            twitch_reauth.get_auth_token(oauth, addr)
        except KeyboardInterrupt:
            pass
    else:
        addr, remote_api_addr, config_path, pconfig_path, core_components = get_args()
        config.CONFIG_FILE = config_path
        run(addr, remote_api_addr, pconfig_path, core_components)
        exit(0)