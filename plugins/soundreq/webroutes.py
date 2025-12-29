from . import soundrequesting
from flask import Blueprint, request, send_file
import os
from web import add_bp_if_new, serve_when_loaded

DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(DIR, "static")
TEMPATES_DIR = os.path.join(DIR, "templates")

web_loaded = False
web_loaded_callback = lambda: web_loaded

soundreqapi = Blueprint("soundreqapi", __name__, url_prefix="/soundreq")

@soundreqapi.get("/sound/<key>")
@serve_when_loaded(web_loaded_callback)
def get_sound(key:str):
    info = soundrequesting.get_sound(key)
    if info is None:
        return "", 404
    return send_file(info["file"])

@soundreqapi.get("/list")
@serve_when_loaded(web_loaded_callback)
def get_sound_list():
    config_parent = soundrequesting.get_configs()
    configs:dict = config_parent.get("Sound-Request", {})
    if "Sounds" in configs:
        sounds = configs["Sounds"]
        if isinstance(sounds, dict):
            return sounds
    return {}

@soundreqapi.post("request")
@serve_when_loaded(web_loaded_callback)
def request_sound():
    key = request.form["key"]
    user = request.form.get("user", None)
    channel = request.form.get("channel", None)
    soundrequesting.add_queue(key, user, channel)
    soundrequesting.invoke_handler()
    return (soundrequesting.get_sound(key) or "") if request.args.get("getname") else "", 201, {"Content-Type": "text/plain"}

@soundreqapi.post("/end")
@serve_when_loaded(web_loaded_callback)
def end_sound():
    soundrequesting.sound_done.set()
    return "", 200


def add_routes(api:Blueprint, add_api=True):
    if add_api:
        add_bp_if_new(api, soundreqapi)