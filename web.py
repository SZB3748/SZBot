from gevent import monkey

monkey.patch_all() #this complains about being called too late, so now it gets called first

import config
from datetime import timedelta
import events
from flask import Flask, render_template, request, send_from_directory
from flask_sock import Server, Sock
from gevent.pywsgi import WSGIServer
import json
from markupsafe import Markup
import os
import requests
import songqueue
import string
import subprocess

HOST = "127.0.0.1"
PORT = 6742
SECRET_FILE = "secret.txt"

DEFAULT_STYLES_FONT = "\"Fragment Mono\""
DEFAULT_STYLES_BG_COLOR = "#000"
DEFAULT_STYLES_TEXT_COLOR = "#fff"
DEFAULT_STYLES_FG_COLOR = "#7f0"
DEFAULT_STYLES_FG2_COLOR = "#041f00"
DEFAULT_STYLES = f"""\
    font-family: {DEFAULT_STYLES_FONT};
    background-color: {DEFAULT_STYLES_BG_COLOR};
    color: {DEFAULT_STYLES_TEXT_COLOR};
    --color-fg: {DEFAULT_STYLES_FG_COLOR};
    --color-fg2: {DEFAULT_STYLES_FG2_COLOR};"""

def build_styles_from_config()->str:
    c = config.read()
    style = c.get("Style", None)
    if isinstance(style, dict):
        fonts_r = style.get("fonts", None)
        if fonts_r is None:
            fonts = DEFAULT_STYLES_FONT
        elif isinstance(fonts_r, str):
            fonts = fonts_r
        elif isinstance(fonts_r, list):
            fonts_items = []
            for item in fonts_r:
                if isinstance(item, str):
                    if " " in item and not ("\"" in item or "'" in item):
                        fonts_items.append(f"\"{item}\"")
                    else:
                        fonts_items.append(item)
            fonts = ", ".join(fonts_items)
        css_styles = [
            "font-family", fonts,
            "background-color", style.get("background_color", DEFAULT_STYLES_BG_COLOR),
            "color", style.get("text_color", DEFAULT_STYLES_TEXT_COLOR),
            "--color-fg", style.get("primary_foreground_color", None) or DEFAULT_STYLES_FG_COLOR,
            "--color-fg2", style.get("secondary_foreground_color", None) or DEFAULT_STYLES_FG2_COLOR,
        ]
        return "\n    ".join(f"{css_styles[i]}: {css_styles[i+1]};" for i in range(0, len(css_styles), 2))
    else:
        return DEFAULT_STYLES
    

def load_config_styles_css()->str:
    loaded = build_styles_from_config()
    return Markup(f"""\
<style>
:root, body {{
    {loaded}
}}
</style>""")

app = Flask(__name__)
app.jinja_env.globals["load_config_styles"] = load_config_styles_css
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

@app.get("/music/overlay")
def music_overlay():
    return render_template("music_overlay.html")

@app.get("/music/thumbnail/<name>")
def music_thumbnail(name:str):
    return send_from_directory(songqueue.THUMBNAILS_DIR, name)

@app.get("/oauth")
def oauth():
    code = request.args["code"]
    configs = config.read(path=config.OAUTH_TWITCH_FILE)
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
    config.write(config_updates={"Token": d["access_token"], "Refresh-Token": d["refresh_token"]}, path=config.OAUTH_TWITCH_FILE)
    return "Restart", 200

def _v_to_dict(v:songqueue.QueuedSong)->dict[str]:
    return {
        "id": v.video_id,
        "duration": songqueue.format_duration(v.duration),
        "start": v.start,
        "title": v.title,
        "thumbnail": v.thumbnail
    }

@app.get("/api/music/queue")
def api_music_queue_get():
    queue_list = []
    with open(songqueue.QUEUE_FILE) as f:
        for line in f:
            if all(c in string.whitespace for c in line):
                continue
            id, duration_s, thumbnail, start_s, title = (line[:-1] if line.endswith("\n") else line).split(" ", 4)
            queue_list.append({
                "id": id,
                "duration": duration_s,
                "start": int(start_s),
                "title": title,
                "thumbnail": thumbnail
            })
    return json.dumps({
        "current": None if songqueue.current_song is None else _v_to_dict(songqueue.current_song),
        "next": None if songqueue.next_song is None else _v_to_dict(songqueue.next_song),
        "queue": queue_list
    }), 200, {"Content-Type": "application/json"}

@app.post("/api/music/queue/push")
def api_music_queue_push():
    url = request.form["url"]
    v = songqueue.get_song(url)
    if v is None:
        events.dispatch(songqueue.QueuedSongEvent(-1, False, video_id=url, title="", duration=timedelta(seconds=0), thumbnail="", start=0))
        return "", 403
    pos = songqueue.push_queue(v)
    events.dispatch(songqueue.QueuedSongEvent.new(pos, True, v))
    return str(pos), 200

@sock.route("/api/music/events")
def api_music_listen(ws:Server):
    bucket = events.new_bucket()
    try:
        while ws.connected:
            ws.receive(0)
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
    purge_s = request.form.get("purge", "false").strip().lower().replace("false", "")
    npurge = not purge_s

    if not count_s.isdigit():
        return "Invalid count", 422
    count = int(count_s)
    pre_skipped = 0
    if count > 0:
        if songqueue.current_song is not None:
            songqueue.save_current_to_playlist = False
            if npurge:
                songqueue.add_to_playlist(songqueue.current_song.video_id)
            songqueue.current_song = None
            #NOTE: cannot remove CURRENT_FILE here, as it is being used by the vlc player; current file is removed on its own during normal operation
            pre_skipped += 1
    else:
        return "0", 200, {"Content-Type": "application/json"}
    if count > 1:
        if songqueue.next_song is not None:
            if npurge:
                songqueue.add_to_playlist(songqueue.next_song.video_id)
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
        skip_count = pre_skipped #to get to this point, the current and/or next songs may have been skipped
        for _ in range(count - pre_skipped):
            index = content.find("\n", cutoff)
            if index < 0:
                break
            if npurge:
                space_index = content.find(" ", cutoff, index)
                if space_index > 0:
                    songqueue.add_to_playlist(content[cutoff:space_index])
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

@app.route("/api/music/playerstate", methods=["GET", "POST"])
def api_music_playerstate():
    if songqueue.current_song is None:
        rtv = "{\"state\": null}"
    else:
        if request.method == "POST":
            state = request.form["state"]
            if state == "play":
                songqueue.vlc_player.play()
            elif state == "pause":
                songqueue.vlc_player.pause()
            else:
                return "Invalid playerstate.", 422
            events.dispatch(events.Event("change_playerstate", {
                "state": state,
                "position": songqueue.vlc_player.get_position() * songqueue.vlc_player.get_length()
            }))
        else:
            state = "play" if songqueue.vlc_player.is_playing() else "pause"
        rtv = json.dumps({
            "state": state,
            "position": songqueue.vlc_player.get_position() * songqueue.vlc_player.get_length()
        })
    return rtv, 200, {"Content-Type": "application/json"}

@app.post("/api/music/seek")
def api_musics_seek():
    if songqueue.current_song is None:
        return
    seconds_s = request.form["seconds"]
    if not seconds_s.isdigit():
        return "Invalid seconds", 422
    seconds = float(seconds_s)
    if os.path.isfile(songqueue.CURRENT_FILE):
        song = songqueue.vlc_instance.media_new(songqueue.CURRENT_FILE)
        song.add_option(f"start-time={seconds}")
        was_playing = songqueue.vlc_player.is_playing()
        events.dispatch(events.Event("change_playerstate", {
            "state": "play" if was_playing else "pause",
            "position": seconds * 1000
        }))
        songqueue.vlc_player.set_media(song)
        if was_playing:
            songqueue.vlc_player.play()
    return "", 200

@app.route("/api/music/b-track", methods=["GET", "POST"])
def api_music_b_track():
    configs = config.read()
    current_b_track = configs.get("B-Track", None)
    index = songqueue.b_track_index

    if request.method == "POST":
        url = request.form["url"]
        if "index" in request.form:
            index_s = request.form["index"]
            if not index_s.isdigit():
                return "Invalid index", 422
            index = int(index_s)
            if index not in songqueue.b_track_order:
                index = songqueue.b_track_index

        if isinstance(current_b_track, dict):
            start = current_b_track.get("start", 1)
        else:
            start = 1

        p = subprocess.Popen(["yt-dlp", url, "-I0", "-O", "playlist:playlist_count"], stdout=subprocess.PIPE)
        out, _ = p.communicate()
        if p.returncode:
            return "Failed to get playlist info.", 500
        
        config.write(config_updates={
            "B-Track": {"url": url, "start": start} if url else None
        })
        songqueue.b_track_playlist = url
        songqueue.b_track_index = songqueue.b_track_order.index(index)
        songqueue.b_track_length = int(out)
    elif isinstance(current_b_track, dict) and current_b_track:
        url = current_b_track["url"]
    else:
        url = None

    return json.dumps({
        "url": url,
        "index": index
    }), 200, {"Content-Type": "application/json"}

@app.get("/api/music/open-queue")
def api_music_open_queue():
    if os.path.isfile(songqueue.QUEUE_FILE):
        subprocess.Popen(["notepad", songqueue.QUEUE_FILE])
        return "", 200
    else:
        return "", 404



def serve():
    server = WSGIServer((HOST, PORT), app)
    server.serve_forever()
