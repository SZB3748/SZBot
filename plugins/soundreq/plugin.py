from . import soundrequesting, twitchcommands, webroutes
import plugins
from threading import Thread
import twitchbot
import web

bot:twitchbot.Bot = None
playerthread:Thread = None
player:soundrequesting.SoundRequestPlayer = None

def on_load(ctx:plugins.LoadEvent):
    global playerthread, player

    _, plugin, _, host_addr, _, api_only, *_ = ctx
    
    soundrequesting.meta = plugin.meta
    webroutes.web_loaded = True

    if not api_only:
        # use host_addr even when local API is just a proxy, allows for
        # easier integration with plugins that modify API behavior
        # (e.g. authentication, logging)
        player_api_addr = f"{host_addr[0]}:{host_addr[1]}"
        player = soundrequesting.SoundRequestPlayer(player_api_addr, host_addr[1] == 443)
        playerthread = Thread(target=player.start, daemon=True)
        print("Starting sound player")
        playerthread.start()

def on_twitch_bot_load(ctx:plugins.TwitchBotLoadEvent):
    global bot
    _, _, _, bot, *_ = ctx
    twitchcommands.add_commands(bot)

def on_unload(ctx:plugins.UnloadEvent):
    global playerthread, player

    _, _, _, _, *_ = ctx
    
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
    _, _, _, _, *_ = ctx
    twitchcommands.remove_commands(bot)


webroutes.add_routes(web.app, web.api)