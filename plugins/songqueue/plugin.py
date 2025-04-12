import songqueueing
import twitchcommands
import webroutes
from flask import Blueprint, Flask
from threading import Thread

cycle:Thread = None

def on_load(ctx:tuple[dict, object, bool, Flask, Blueprint, object]):
    global cycle

    _, _, is_startup, app, api, _, *_ = ctx

    print("starting music queue")
    cycle = songqueueing.run_song_cycle()

    if is_startup:
        webroutes.add_routes(app, api)

def on_twitch_bot_load():
    twitchcommands.add_commands(...) #TODO

def on_unload(ctx:tuple[dict, object, bool, Exception|None]):

    _, _, _, _, *_ = ctx

    songqueueing.song_done.set()
    songqueueing.stop_loop.set()
    print("Waiting for song cycle to stop...")
    cycle.join(5)
    if cycle.is_alive():
        print("Song cycle failed to stop after 5 seconds")
    else:
        print("Song cycle stopped")

def on_twitch_bot_unload():
    twitchcommands.remove_commands(...) #TODO