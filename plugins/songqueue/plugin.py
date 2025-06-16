from . import playlist, songplaying, songqueueing, twitchcommands, webroutes
import config
import os
import plugins
import subprocess
import sys
from threading import Thread
import twitchbot
import web

DIR = os.path.dirname(__file__)
PLAYER_FILE = os.path.join(DIR, "songplayer_process.py")

cycle:Thread = None
playerprocess:subprocess.Popen = None
player:songplaying.SongPlayer = None
bot:twitchbot.Bot = None

def on_load(ctx:plugins.LoadEvent):
    global cycle, player, playerprocess

    _, plugin, _, host_addr, remote_api, api_only, *_ = ctx

    songqueueing.meta = plugin.meta
    webroutes.web_loaded = True

    if remote_api is None:
        if songqueueing.youtube_api is None:
            songqueueing.youtube_api = playlist.get_authenticated_service()
        queue = songqueueing.main_queue = songqueueing.SongQueue()
        print("Starting music queue")
        cycle = songqueueing.run_song_cycle(queue, daemon=True)

    if not api_only:
        # use host_addr even when local API is just a proxy, allows for
        # easier integration with plugins that modify API behavior
        # (e.g. authentication, logging)
        player_api_addr = f"{host_addr[0]}:{host_addr[1]}"
        configs_parent = songqueueing.get_configs()
        configs:dict = configs_parent.get("Song-Queue", {})
        if "Output-Device" in configs:
            output_device = configs["Output-Device"]
        else:
            output_device = None
        print("Starting music player")
        playerprocess = subprocess.Popen([sys.executable, PLAYER_FILE, player_api_addr, output_device])

def on_twitch_bot_load(ctx:plugins.TwitchBotLoadEvent):
    global bot
    _, _, _, bot, *_ = ctx
    print("Adding songqueue commands")
    twitchcommands.add_commands(bot)

def on_unload(ctx:plugins.UnloadEvent):
    global cycle, player, playerprocess

    _, _, _, _, *_ = ctx

    webroutes.web_loaded = False
    if songqueueing.main_queue is not None:
        songqueueing.main_queue.current_tracker.end()
        songqueueing.main_queue.stop_loop.set()
    if player is not None:
        player.end()

    if cycle is not None:
        print("Waiting for song cycle to stop...")
        cycle.join(5)
        if cycle.is_alive():
            print("Song cycle failed to stop after 5 seconds")
        else:
            print("Song cycle stopped")
    # if playerthread is not None:
    #     print("Waiting for music player to stop...")
    #     playerthread.join(5)
    #     if playerthread.is_alive():
    #         print("Music player failed to stop after 5 seconds")
    #     else:
    #         print("Music player stopped")
    if playerprocess is not None:
        playerprocess.terminate()

    songqueueing.main_queue = None
    cycle = None
    player = None
    playerprocess = None

def on_twitch_bot_unload(ctx:plugins.TwitchBotUnloadEvent):
    _, _, _, _, *_ = ctx
    print("Removing songqueue commands")
    twitchcommands.remove_commands(bot)

oauth = config.read(path=playlist.OAUTH_YOUTUBE_FILE)
if not ("installed" in oauth and "scopes" in oauth):
    print("You must create a youtube_oauth.json file with the OAuth Credentials gotten from Google Cloud Console.\nMake sure the OAuth Credentials are under the \"installed\" field and add a list of scopes under the \"scopes\" field (\"scopes\" should be at the same level as \"installed\", NOT inside of \"installed\").")
    exit(-1)

webroutes.add_routes(web.app, web.api)