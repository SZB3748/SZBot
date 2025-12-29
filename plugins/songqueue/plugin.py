from . import playlist
import config
import os
import plugins

DIR = os.path.dirname(__file__)


def on_load(ctx:plugins.LoadEvent):
    ...

def on_twitch_bot_load(ctx:plugins.TwitchBotLoadEvent):
    ...

def on_unload(ctx:plugins.UnloadEvent):
    ...

def on_twitch_bot_unload(ctx:plugins.TwitchBotUnloadEvent):
    ...

oauth = config.read(path=playlist.OAUTH_YOUTUBE_FILE)
if not ("installed" in oauth and "scopes" in oauth):
    print("You must create a youtube_oauth.json file with the OAuth Credentials gotten from Google Cloud Console.\nMake sure the OAuth Credentials are under the \"installed\" field and add a list of scopes under the \"scopes\" field (\"scopes\" should be at the same level as \"installed\", NOT inside of \"installed\").")
    exit(-1)