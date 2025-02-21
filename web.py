from gevent import monkey

monkey.patch_all() #this complains about being called too late, so now it gets called first

import config
from datetime import timedelta
import events
from flask import Flask, render_template, request
from flask_sock import Server, Sock
from gevent.pywsgi import WSGIServer
import json
import os
import requests
import songqueue
import string

HOST = "127.0.0.1"
PORT = 8080
SECRET_FILE = "secret.txt"

app = Flask(__name__)
app.url_map.strict_slashes = False
app.config["TEMPLATES_AUTO_RELOAD"] = True
with open(SECRET_FILE) as f:
    app.secret_key = f.read()
sock = Sock(app)

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/music")
def music_interface():
    return render_template("music.html")

@app.get("/oauth")
def oauth():
    code = request.args["code"]
    configs = config.read()
    r = requests.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": configs["Client-Id"],
        "client_secret": configs["Client-Secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": request.base_url
    })
    if not r.ok:
        print("oauth failure")
        return r.text, r.status_code
    d = r.json()
    config.write(config_updates={"Token": d["access_token"], "Refresh-Token": d["refresh_token"]})
    return "Restart", 200

def _v_to_dict(v:songqueue.QueuedVideo)->dict[str]:
    return {
        "id": v.video_id,
        "duration": songqueue.format_duration(v.duration),
        "start": v.start,
        "title": v.title
    }

@app.get("/api/music/queue")
def api_music_queue_get():
    queue_list = []
    with open(songqueue.QUEUE_FILE) as f:
        for line in f:
            if all(c in string.whitespace for c in line):
                continue
            id, duration_s, start_s, title = (line[:-1] if line.endswith("\n") else line).split(" ", 3)
            queue_list.append({
                "id": id,
                "duration": duration_s,
                "start": int(start_s),
                "title": title
            })
    return json.dumps({
        "current": None if songqueue.current_song is None else _v_to_dict(songqueue.current_song),
        "next": None if songqueue.next_song is None else _v_to_dict(songqueue.next_song),
        "queue": queue_list
    }), 200, {"Content-Type": "application/json"}

@app.post("/api/music/queue/push")
def api_music_queue_push():
    url = request.form["url"]
    v = songqueue.get_video(url)
    if v is None:
        events.dispatch(songqueue.QueuedSongEvent(-1, False, video_id=url, title="", duration=timedelta(seconds=0), start=0))
        return "", 403
    pos = songqueue.push_queue(v)
    events.dispatch(songqueue.QueuedSongEvent.new(pos, True, v))
    return str(pos), 200

@sock.route("/api/music/queue/events")
def api_music_queue_listen(ws:Server):
    bucket = events.new_bucket()
    try:
        while ws.connected:
            for event in bucket.dump():
                ws.send(event.to_json())
    finally:
        events.remove_bucket(bucket)

@app.post("/api/music/overlay/persistent")
def api_music_set_overlay_persistent():
    value = request.form.get("value", "false").strip().lower() == "true"
    events.dispatch(events.Event("overlay_persistence_change", {"value": value}))
    return "", 200

@app.post("/api/music/queue/skip")
def api_music_queue_skip():
    count_s = request.form.get("count", "1")
    if not count_s.isdigit():
        return "Invalid count", 422
    count = int(count_s)
    pre_skipped = 0
    if count > 0:
        if songqueue.current_song is not None:
            songqueue.current_song = None
            #NOTE: cannot remove CURRENT_FILE here, as it is being used by the vlc player; current file is removed on its own during normal operation
            pre_skipped += 1
    else:
        return "0", 200, {"Content-Type": "application/json"}
    if count > 1:
        if songqueue.next_song is not None:
            songqueue.next_song = None
            if os.path.isfile(songqueue.NEXT_FILE):
                os.remove(songqueue.NEXT_FILE)
            pre_skipped += 1
    elif pre_skipped: #count == 1 and current was skipped
        songqueue.song_done.set()
        return "1", 200, {"Content-Type": "application/json"}

    with open(songqueue.QUEUE_FILE, "r+") as f:
        content = f.read()
        cutoff = 0
        skip_count = pre_skipped #to get to this point, the current and/or next videos may have been skipped
        for _ in range(count - pre_skipped):
            index = content.find("\n", cutoff)
            if index < 0:
                break
            cutoff = index+1
            if all(content[i] in string.whitespace for i in range(cutoff, index)):
                skip_count += 1
        
        if cutoff > 0:
            f.seek(0)
            f.truncate()
            try:
                new_content = content[cutoff:]
                if any(c not in string.whitespace for c in new_content):
                    f.write(new_content)
                    songqueue.queue_populated.set()
                else:
                    songqueue.queue_populated.clear()
            except:
                f.write(content)
                raise
            finally:
                songqueue.song_done.set()
        else:
            songqueue.song_done.set()
    return str(skip_count), 200, {"Content-Type": "application/json"}

@app.route("/api/music/song/playerstate", methods=["GET", "POST"])
def api_music_queue_playerstate():
    if request.method == "POST":
        state = request.form["state"]
        if state == "play":
            songqueue.vlc_player.play()
        elif state == "pause":
            songqueue.vlc_player.pause()
        else:
            return "Invalid playerstate.", 422
    else:
        state = "play" if songqueue.vlc_player.is_playing() else "pause"

    if songqueue.current_song is None:
        rtv = "{\"state\": null}"
    else:
        rtv = json.dumps({
            "state": state,
            "position": songqueue.vlc_player.get_position()
        })
    return rtv, 200, {"Content-Type": "application/json"}


def serve():
    server = WSGIServer((HOST, PORT), app)
    server.serve_forever()
