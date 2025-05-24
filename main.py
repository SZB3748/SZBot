from gevent import monkey

monkey.patch_all() #must be called first

import argparse
import config
import plugins
import traceback
import twitchbot
from urllib.parse import quote
import web

OAUTH_ENDPOINT = "https://id.twitch.tv/oauth2/authorize"

parser = argparse.ArgumentParser(description="SZBot main program.")
parser.add_argument("-d", "--addr", default=f"{web.HOST}:{web.PORT}")

def get_addr()->tuple[str, int]:
    args = parser.parse_args()
    addr:str = args.addr
    if ":" in addr:
        host, port = addr.split(":", 1)
        if host and port:
            if port.isdigit():
                return host, int(port)
            else:
                print("Address port must be an integer")
                exit(-1)
        elif port and not port.isdigit():
            print("Address port must be an integer")
            exit(-1)
        else:
            return host or web.HOST, int(port) if port else web.PORT
    elif addr.isdecimal():
        return web.HOST, int(addr)
    else:
        return addr, web.PORT

def get_auth_token(oauth:dict[str], addr:tuple[str, int]=(web.HOST, web.PORT)):
    import webbrowser
    host, port, *_ = addr
    redirect = f"http://{host}:{port}/oauth"
    scope = " ".join(twitchbot.OAUTH_SCOPES)
    url = f"{OAUTH_ENDPOINT}?response_type=code&client_id={oauth["Client-Id"]}&redirect_uri={quote(redirect)}&scope={quote(scope)}"
    try:
        webbrowser.open(url)
        print("Opening", url, "in your default browser")
    except:
        print("Could not automatically find a browser, open", url, "in a browser")
    web.serve(host, port)

def run(addr:tuple[str, int]=(web.HOST, web.PORT)):
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
                plugin.load((plugin_list, plugin, True, web.app, web.api, web.sock))
        print("loaded plugins")
    else:
        print("no plugins made it into the load order\nmake sure that any dependenant plugins are enabled")
    plugins.shared_plugins_list = plugin_list
    print("bot must be started manually")
    print("starting web server")
    e = None
    try:
        web.serve(host=addr[0], port=addr[1])
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
            addr = get_addr()
            get_auth_token(oauth, addr)
        except KeyboardInterrupt:
            pass
        exit(0)
    else:
        addr = get_addr()
        run(addr)