import web

import config
import plugins
import twitchbot
from urllib.parse import quote

OAUTH_ENDPOINT = "https://id.twitch.tv/oauth2/authorize"

def get_auth_token(oauth:dict[str]):
    import webbrowser
    redirect = f"http://localhost:6742/oauth"
    scope = " ".join(twitchbot.OAUTH_SCOPES)
    url = f"{OAUTH_ENDPOINT}?response_type=code&client_id={oauth["Client-Id"]}&redirect_uri={quote(redirect)}&scope={quote(scope)}"
    webbrowser.open(url)
    print("Opening", url, "in your default browser")
    web.serve()


def run():
    print("reading plugin list")
    plugin_list = plugins.read_plugin_data()
    plugin_enabled_count = sum(1 for plugin in plugin_list.values() if plugin.module is not None)
    print("read", len(plugin_list), "plugins with", plugin_enabled_count, "enabled plugins")
    print("loading enabled plugins")
    for plugin in plugin_list.values():
        if plugin.module is not None:
            plugin.load((plugin_list, plugin, True, web.app, web.api, web.sock))
    print("loaded plugins")
    plugins.shared_plugins_list = plugin_list
    print("bot must be started manually")
    print("starting web server")
    e = None
    try:
        web.serve()
    except KeyboardInterrupt:
        pass
    except Exception as _e:
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
            get_auth_token(oauth)
        except KeyboardInterrupt:
            pass
        exit(0)
    else:
        run()