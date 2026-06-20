from . import soundplayer

from flask import Blueprint, request
import os
from web import add_bp_if_new, serve_when_loaded

DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(DIR, "static")
TEMPATES_DIR = os.path.join(DIR, "templates")

web_loaded = False
web_loaded_callback = lambda: web_loaded

soundsapi = Blueprint("soundsapi", __name__, url_prefix="/sounds")

@soundsapi.post("enqueue")
@serve_when_loaded(web_loaded_callback)
def enqueue_sound():
    media_name = request.form["name"]
    uid, l = soundplayer.main_player.add_to_queue(media_name, soundplayer.LOC_TYPE_LOCAL) #TODO decide type and url_prefix value
    return f"{str(uid)}\n{l-1}", 200, {"Content-Type":"text/plain"}

def add_routes(api:Blueprint, add_api=True):
    if add_api:
        add_bp_if_new(api, soundsapi)
