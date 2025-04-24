import config
import plugins
import soundrequesting
import twitchbot
import twitchcommands
import webroutes

bot:twitchbot.Bot = None

def on_load(ctx:plugins.LoadEvent):

    _, plugin, is_startup, app, api, _, *_ = ctx

    soundrequesting.meta = plugin.meta

    if is_startup:
        soundrequesting.init()
        webroutes.add_routes(app, api)

def on_twitch_bot_load(ctx:plugins.TwitchBotLoadEvent):
    global bot
    _, _, _, bot, *_ = ctx
    twitchcommands.add_commands(bot)

def on_unload(ctx:plugins.UnloadEvent):
    _, _, _, _, *_ = ctx
    
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

def on_twitch_bot_unload(ctx:plugins.TwitchBotUnloadEvent):
    _, _, _, _, *_ = ctx
    twitchcommands.remove_commands(bot)