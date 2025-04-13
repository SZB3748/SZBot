import config
import playlist
import plugins
import songqueueing
from threading import Thread
import twitchbot
import twitchcommands
import webroutes

cycle:Thread = None
bot:twitchbot.Bot = None

def on_load(ctx:plugins.LoadEvent):
    global cycle

    _, _, is_startup, app, api, _, *_ = ctx

    print("starting music queue")
    cycle = songqueueing.run_song_cycle()

    if is_startup:
        webroutes.add_routes(app, api)
        songqueueing.youtube_api = playlist.get_authenticated_service()

def on_twitch_bot_load(ctx:plugins.TwitchBotLoadEvent):
    global bot
    _, _, _, bot, *_ = ctx
    twitchcommands.add_commands(bot)

def on_unload(ctx:plugins.UnloadEvent):
    _, _, _, _, *_ = ctx

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
    twitchcommands.remove_commands(bot)

oauth = config.read(path=playlist.OAUTH_YOUTUBE_FILE)
if not ("installed" in oauth and "scopes" in oauth):
    print("You must create a youtube_oauth.json file with the OAuth Credentials gotten from Google Cloud Console.\nMake sure the OAuth Credentials are under the \"installed\" field and add a list of scopes under the \"scopes\" field (\"scopes\" should be at the same level as \"installed\", NOT inside of \"installed\").")
    exit(-1)