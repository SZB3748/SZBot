from . import soundrequesting, twitchcommands, webroutes
import plugins
from threading import Thread
import twitchbot
import web

COMPONENT_API = "api"
COMPONENT_TWITCHBOT_COMMANDS = "twitchbot:commands"
COMPONENT_SOUNDPLAYER = "soundplayer"

bot:twitchbot.Bot = None
playerthread:Thread = None
player:soundrequesting.SoundRequestPlayer = None

def on_load(ctx:plugins.LoadEvent):
    global playerthread, player
    
    soundrequesting.meta = ctx.plugin.meta
    webroutes.web_loaded = True
    
    m_api = ctx.plugin.get_component_mode(COMPONENT_API)
    m_soundplayer = ctx.plugin.get_component_mode(COMPONENT_SOUNDPLAYER)

    if ctx.is_start:
        webroutes.add_routes(web.api, m_api == plugins.COMPONENT_MODE_NORMAL)
        if m_api == plugins.COMPONENT_MODE_REMOTE:
            web.create_component_proxy(ctx.remote_api_addr, web.api, webroutes.soundreqapi.name, webroutes.soundreqapi.url_prefix, socket=False)

    assert m_soundplayer != plugins.COMPONENT_MODE_REMOTE, "Sound Player has no remote mode."
    if m_soundplayer == plugins.COMPONENT_MODE_NORMAL:
        player = soundrequesting.SoundRequestPlayer(f"{ctx.host_addr[0]}:{ctx.host_addr[1]}", ctx.host_addr[1] == 443)
        playerthread = Thread(target=player.start, daemon=True)
        print("Starting sound player")
        playerthread.start()

def on_twitch_bot_load(ctx:plugins.TwitchBotLoadEvent):
    global bot
    m_commands = ctx.plugin.get_component_mode(COMPONENT_TWITCHBOT_COMMANDS)
    assert m_commands != plugins.COMPONENT_MODE_REMOTE, "Twitch bot commands has no remote mode."
    if m_commands == plugins.COMPONENT_MODE_NORMAL:
        bot = ctx.bot
        print("Adding soundreq twitch commands")
        twitchcommands.add_commands(bot)

def on_unload(ctx:plugins.UnloadEvent):
    global playerthread, player
    
    webroutes.web_loaded = False

    if player is not None:
        player.end()
    
    if soundrequesting.queue_handler is not None:
        old = soundrequesting.queue_handler
        soundrequesting.queue_handler = None
        soundrequesting.sound_done.set()

        print("Waiting for sound request handler to stop...")
        old.join(5)
        if old.is_alive():
            print("Sound request handler failed to stop after 5 seconds")
        else:
            print("Sound request handler stopped")
    
    if playerthread is not None:
        print("Wainting for sound player to stop...")
        playerthread.join(5)
        if playerthread.is_alive():
            print("Sound player failed to stop after 5 seconds")
        else:
            print("Sound player stopped")
        
    playerthread = None
    player = None

def on_twitch_bot_unload(ctx:plugins.TwitchBotUnloadEvent):
    global bot
    if bot is not None:
        print("Removing soundreq twitch commands")
        twitchcommands.remove_commands(bot)
        bot = None
