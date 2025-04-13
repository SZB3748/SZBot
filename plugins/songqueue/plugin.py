import bot
import plugins
import songqueueing
from threading import Thread
import twitchcommands
import webroutes

cycle:Thread = None
twitch_bot:bot.Bot = None

def on_load(ctx:plugins.LoadEvent):
    global cycle

    _, _, is_startup, app, api, _, *_ = ctx

    print("starting music queue")
    cycle = songqueueing.run_song_cycle()

    if is_startup:
        webroutes.add_routes(app, api)

def on_twitch_bot_load(ctx:plugins.TwitchBotLoadEvent):
    global twitch_bot
    _, _, _, twitch_bot, *_ = ctx
    twitchcommands.add_commands(twitch_bot)

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
    global twitch_bot
    _, _, _, _, *_ = ctx
    twitchcommands.remove_commands(twitch_bot)
    twitch_bot = None