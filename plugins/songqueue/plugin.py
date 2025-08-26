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


COMPONENT_INTERFACE = "interface"
COMPONENT_OVERLAY = "overlay"
COMPONENT_API = "api"
COMPONENT_SONGQUEUE = "songqueue"
COMPONENT_SONGPLAYER = "songplayer"
COMPONENT_TWITCHBOT_COMMANDS = "twitchbot:commands"

cycle:Thread = None
playerprocess:subprocess.Popen = None
player:songplaying.SongPlayer = None
bot:twitchbot.Bot = None

def on_load(ctx:plugins.LoadEvent):
    global cycle, player, playerprocess

    songqueueing.meta = ctx.plugin.meta
    webroutes.web_loaded = True

    m_interface = ctx.plugin.get_component_mode(COMPONENT_INTERFACE)
    m_overlay = ctx.plugin.get_component_mode(COMPONENT_OVERLAY)
    m_api = ctx.plugin.get_component_mode(COMPONENT_API)
    m_songqueue = ctx.plugin.get_component_mode(COMPONENT_SONGQUEUE)
    m_songplayer = ctx.plugin.get_component_mode(COMPONENT_SONGPLAYER)

    if ctx.is_start:
        webroutes.add_routes(web.app, web.api, m_interface == plugins.COMPONENT_MODE_NORMAL, m_overlay == plugins.COMPONENT_MODE_NORMAL, m_api == plugins.COMPONENT_MODE_NORMAL)
        rinterface = m_interface == plugins.COMPONENT_MODE_REMOTE
        roverlay = m_overlay == plugins.COMPONENT_MODE_REMOTE
        vmusicpages_parent = webroutes.Blueprint("proxy_musicparent", __name__, static_folder=webroutes.musicpages_parent.static_folder, template_folder=webroutes.musicpages_parent.template_folder, static_url_path=webroutes.musicpages_parent.static_url_path)
        if rinterface:
            web.create_component_proxy(ctx.remote_api_addr, vmusicpages_parent, webroutes.musicpages.name, webroutes.musicpages.url_prefix, socket=False)
        if roverlay:
            web.create_component_proxy(ctx.remote_api_addr, vmusicpages_parent, webroutes.musicoverlays.name, webroutes.musicoverlays.url_prefix, socket=False)
        if rinterface or roverlay:
            web.add_bp_if_new(web.app, vmusicpages_parent)
        if m_api == plugins.COMPONENT_MODE_REMOTE:
            web.create_component_proxy(ctx.remote_api_addr, web.api, webroutes.musicapi.name, webroutes.musicapi.url_prefix)


    assert m_songqueue != plugins.COMPONENT_MODE_REMOTE, "Songqueue has no remote mode."
    if m_songqueue == plugins.COMPONENT_MODE_NORMAL:
        if songqueueing.youtube_api is None:
            songqueueing.youtube_api = playlist.get_authenticated_service()
        queue = songqueueing.main_queue = songqueueing.SongQueue()
        print("Starting music queue")
        cycle = songqueueing.run_song_cycle(queue, daemon=True)

    if m_songplayer == plugins.COMPONENT_MODE_NORMAL:
        player_api_addr = f"{ctx.host_addr[0]}:{ctx.host_addr[1]}"
    elif m_songplayer == plugins.COMPONENT_MODE_REMOTE:
        assert ctx.remote_api_addr is not None, "Cannot start songplayer in remote mode, missing remote API address."
        player_api_addr = ctx.remote_api_addr
    else:
        player_api_addr = None
    
    if player_api_addr is not None:
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
    m_commands = ctx.plugin.get_component_mode(COMPONENT_TWITCHBOT_COMMANDS)
    assert m_commands != plugins.COMPONENT_MODE_REMOTE, "Twitch bot commands has no remote mode."
    if m_commands == plugins.COMPONENT_MODE_NORMAL:
        bot = ctx.bot
        print("Adding songqueue twitch commands")
        twitchcommands.add_commands(bot)

def on_unload(ctx:plugins.UnloadEvent):
    global cycle, player, playerprocess

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
    if playerprocess is not None:
        playerprocess.terminate()

    songqueueing.main_queue = None
    cycle = None
    player = None
    playerprocess = None

def on_twitch_bot_unload(ctx:plugins.TwitchBotUnloadEvent):
    global bot
    if bot is not None:
        print("Removing songqueue twitch commands")
        twitchcommands.remove_commands(bot)
        bot = None

oauth = config.read(path=playlist.OAUTH_YOUTUBE_FILE)
if not ("installed" in oauth and "scopes" in oauth):
    print("You must create a youtube_oauth.json file with the OAuth Credentials gotten from Google Cloud Console.\nMake sure the OAuth Credentials are under the \"installed\" field and add a list of scopes under the \"scopes\" field (\"scopes\" should be at the same level as \"installed\", NOT inside of \"installed\").")
    exit(-1)