from . import playlist, songqueueing, twitchcommands, webroutes
import config
import plugins
from threading import Thread
import twitchbot
import web

cycle:Thread = None
bot:twitchbot.Bot = None

def on_load(ctx:plugins.LoadEvent):
    global cycle

    _, plugin, _, *_ = ctx

    songqueueing.meta = plugin.meta
    webroutes.web_loaded = True

    if songqueueing.youtube_api is None:
        songqueueing.youtube_api = playlist.get_authenticated_service()

    print("Starting music queue")
    cycle = songqueueing.run_song_cycle(daemon=True)

def on_twitch_bot_load(ctx:plugins.TwitchBotLoadEvent):
    global bot
    _, _, _, bot, *_ = ctx
    print("Adding songqueue commands")
    twitchcommands.add_commands(bot)

def on_unload(ctx:plugins.UnloadEvent):
    _, _, _, _, *_ = ctx

    webroutes.web_loaded = False
    songqueueing.song_done.set()
    songqueueing.stop_loop.set()
    print("Waiting for song cycle to stop...")
    cycle.join(5)
    if cycle.is_alive():
        print("Song cycle failed to stop after 5 seconds")
    else:
        print("Song cycle stopped")

def on_twitch_bot_unload(ctx:plugins.TwitchBotUnloadEvent):
    _, _, _, _, *_ = ctx
    print("Removing songqueue commands")
    twitchcommands.remove_commands(bot)

oauth = config.read(path=playlist.OAUTH_YOUTUBE_FILE)
if not ("installed" in oauth and "scopes" in oauth):
    print("You must create a youtube_oauth.json file with the OAuth Credentials gotten from Google Cloud Console.\nMake sure the OAuth Credentials are under the \"installed\" field and add a list of scopes under the \"scopes\" field (\"scopes\" should be at the same level as \"installed\", NOT inside of \"installed\").")
    exit(-1)

webroutes.add_routes(web.app, web.api)