from flask import Blueprint, Flask, request, send_file
import os
import soundrequesting

DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(DIR, "static")
TEMPATES_DIR = os.path.join(DIR, "templates")

soundreqapi = Blueprint("soundreqapi", __name__, url_prefix="/soundreq")

@soundreqapi.get("/sound/<key>")
def get_sound(key:str):
    info = soundrequesting.get_sound(key)
    if info is None:
        return "", 404
    return send_file(info["file"])

@soundreqapi.post("request")
def request_sound():
    key = request.form["key"]
    soundrequesting.add_queue(key)
    soundrequesting.invoke_handler()
    return "", 201

def add_routes(app:Flask, api:Blueprint):
    api.register_blueprint(soundreqapi)