from gevent import monkey

monkey.patch_all() #must be called first

import argparse
import config
import plugins
import traceback
import twitch_reauth
import web

parser = argparse.ArgumentParser(description="SZBot main program.")
parser.add_argument("-d", "--addr", default=f"{web.HOST}:{web.PORT}", help="Stores the address to host the flask app on.")
parser.add_argument("--remote-api", default=None, help="The IP/Domain:Port to connect to for API calls. Will be used to make a uri_host: \"http(s)://{api}/\". The API routes on the local flask app will act as a proxy.")
parser.add_argument("--api-only", action="store_true", help="Only serve/handle the API endpoints.")

def get_args()->tuple[tuple[str, int], str|None, bool]:
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
    
    return addr, args.remote_api, args.api_only

def run(addr:tuple[str, int]=(web.HOST, web.PORT), remote_api_addr:str=None, api_only=False):
    print("reading plugin list")
    plugin_list = plugins.read_plugin_data()
    plugin_enabled_count = sum(1 for plugin in plugin_list.values() if plugin.module is not None and plugin.startup_load)
    print("read", len(plugin_list), "plugins with", plugin_enabled_count, f"enabled plugin{"s" * (not plugin_enabled_count)}")
    print("generating plugin load order")
    load_order = plugins.generate_load_order(plugin_list)
    if load_order:
        print("loading enabled plugins")
        for plugin_name in load_order:
            plugin = plugin_list[plugin_name]
            if plugin.module is not None and plugin.startup_load:
                plugin.load((plugin_list, plugin, True, addr, remote_api_addr, api_only))
        print("loaded plugins")
    else:
        print("no plugins made it into the load order\nmake sure that any dependenant plugins are enabled")
    plugins.shared_plugins_list = plugin_list
    print("bot must be started manually")
    print("starting web server")
    e = None
    try:
        web.serve(host=addr[0], port=addr[1], remote_api_addr=remote_api_addr, api_only=api_only)
    except KeyboardInterrupt:
        pass
    except Exception as _e:
        traceback.print_exception(_e)
        e = _e
    
    print("unloading enabled plugins")
    for plugin in plugin_list.values():
        if plugin.module is not None:
            plugin.unload((plugin_list, plugin, True, e))
    print("unloaded plugins")

if __name__ == "__main__":
    oauth = config.read(path=config.OAUTH_TWITCH_FILE)
    if not ("Client-Id" in oauth and "Client-Secret" in oauth):
        print("You must create an oauth_twitch.json file with your twitch application's Client-Id and Client-Secret.")
    elif "Token" not in oauth:
        try:
            addr, _, _ = get_args()
            twitch_reauth.get_auth_token(oauth, addr)
        except KeyboardInterrupt:
            pass
        exit(0)
    else:
        addr, remote_api_addr, api_only = get_args()
        run(addr, remote_api_addr, api_only)