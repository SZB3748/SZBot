from . import handler
import audioop
from flask import Blueprint, Flask, request, Response
from flask_sock import Server
import os
from uuid import UUID
from web import add_bp_if_new, serve_when_loaded, sock

DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(DIR, "static")
TEMPATES_DIR = os.path.join(DIR, "templates")
AUDIO_STREAM_MIMETYPE = "audio/x-wav"

web_loaded = False
web_loaded_callback = lambda: web_loaded
main_handler = handler.MicrophoneHandler()

microphone_parent = Blueprint("microphoneparent", __name__, static_folder=STATIC_DIR, static_url_path="/static/microphone")
microphonepages = Blueprint("microphone", __name__, url_prefix="/microphone", template_folder=TEMPATES_DIR)
microphoneapi = Blueprint("microphoneapi", __name__, url_prefix="/microphone")

@microphoneapi.get("/list")
@serve_when_loaded(web_loaded_callback)
def route_mic_list():
    return {
        str(id):mic.__getstate__() for id, mic in main_handler.mics.items()
    }, 200

# @sock.route("/frame/stream", bp=microphoneapi)
# @serve_when_loaded(web_loaded_callback)
# def route_mic_stream(ws:Server):
#     mic_id = UUID(request.args["id"])
#     #check in
    
#     bucket = main_handler.new_bucket(mic_id)
#     if isinstance(bucket, handler.MicDisabledException):
#         ws.close(4422, f"Mic disabled: {bucket}")
#         return
    
#     if bucket is None:
#         ws.close(4404, "Mic not found from given ID.")
#         return
#     try:
#         while ws.connected:
#             bucket.wait()
#             for frame in bucket.get_frames():
#                 ws.send(frame)
#     except KeyboardInterrupt:
#         ws.close()
#     finally:
#         main_handler.drop_bucket(bucket)

@microphoneapi.get("/frame/stream")
@serve_when_loaded(web_loaded_callback)
def route_mic_stream():
    mic_id = UUID(request.args["id"])
    #check in
    try:
        bucket = main_handler.new_bucket(mic_id)
    except handler.MicDisabledException as e:
        return f"Mic disabled: {e}", 422
    if bucket is None:
        return "Mic not found from given ID.", 404
    def r_handler():
        try:
            while True:
                bucket.wait()
                for (frame, *_) in bucket.get_frames():
                    yield frame
        except KeyboardInterrupt:
            main_handler.do_handle = False
    r = Response(r_handler(), 200, mimetype=AUDIO_STREAM_MIMETYPE)
    r.call_on_close(lambda: main_handler.drop_bucket(bucket))
    return r

@microphoneapi.get("/volume/stream")
@serve_when_loaded(web_loaded_callback)
def route_volume_stream():
    mic_id = UUID(request.args["id"])
    threshold = int(request.args.get("threshold", 0))
    byte_count = int(request.args.get("bytes", 2))
    #check in
    try:
        bucket = main_handler.new_bucket(mic_id)
    except handler.MicDisabledException as e:
        return f"Mic disabled: {e}", 422
    if bucket is None:
        return "Mic not found from given ID.", 404
    def r_handler():
        try:
            while True:
                bucket.wait()
                for (frame, _, channels) in bucket.get_frames():
                    volume = audioop.rms(frame, channels)
                    if volume >= threshold:
                        yield volume.to_bytes(byte_count, "big", signed=False)
        except KeyboardInterrupt:
            main_handler.do_handle = False
    r = Response(r_handler(), 200, mimetype="application/octet-stream")
    r.call_on_close(lambda: main_handler.drop_bucket(bucket))
    return r
    

def add_routes(app:Flask, api:Blueprint, add_interface=True, add_api=True):
    if add_interface:
        add_bp_if_new(microphone_parent, microphonepages)
        add_bp_if_new(app, microphone_parent)
    if add_api:
        add_bp_if_new(api, microphoneapi)