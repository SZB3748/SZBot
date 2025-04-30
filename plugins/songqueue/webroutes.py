from . import songqueueing
import config
from datetime import timedelta
import events
from flask import Blueprint, Flask, render_template, request, send_from_directory
import json
import os
import random
import re
import string
import subprocess
from web import serve_when_loaded


DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(DIR, "static")
TEMPATES_DIR = os.path.join(DIR, "templates")

web_loaded = False
web_loaded_callback = lambda: web_loaded

musicpages_parent = Blueprint("musicparent", __name__, static_folder=STATIC_DIR, static_url_path="/static/music")
musicpages = Blueprint("music", __name__, url_prefix="/music", template_folder=TEMPATES_DIR)
musicapi = Blueprint("musicapi", __name__, url_prefix="/music")

@musicpages.get("/")
@serve_when_loaded(web_loaded_callback)
def music_interface():
    return render_template("music.html")

@musicpages.get("/overlay")
@serve_when_loaded(web_loaded_callback)
def music_overlay():
    return render_template("music_overlay.html")

@musicpages.get("/thumbnail/<name>")
@serve_when_loaded(web_loaded_callback)
def music_thumbnail(name:str):
    return send_from_directory(songqueueing.THUMBNAILS_DIR, name)

def _v_to_dict(v:songqueueing.QueuedSong)->dict[str]:
    return {
        "id": v.video_id,
        "duration": songqueueing.format_duration(v.duration),
        "start": v.start,
        "title": v.title,
        "thumbnail": v.thumbnail
    }

@musicapi.get("/queue")
@serve_when_loaded(web_loaded_callback)
def api_music_queue_get():
    queue_list = []
    with open(songqueueing.QUEUE_FILE) as f:
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
        "current": None if songqueueing.current_song is None else _v_to_dict(songqueueing.current_song),
        "next": None if songqueueing.next_song is None else _v_to_dict(songqueueing.next_song),
        "queue": queue_list
    }), 200, {"Content-Type": "application/json"}

@musicapi.post("/queue/push")
@serve_when_loaded(web_loaded_callback)
def api_music_queue_push():
    url = request.form["url"]
    configs_parent = songqueueing.get_configs()
    c:dict = configs_parent.get("Song-Queue", {})
    blacklist = c.get("Song-Blacklist", None)
    if not isinstance(blacklist, list):
        blacklist = []

    if url in blacklist:
        return url, 403

    v = songqueueing.get_song(url)
    if v is None:
        events.dispatch(songqueueing.QueuedSongEvent(-1, False, video_id=url, title="", duration=timedelta(seconds=0), thumbnail="", start=0))
        return "", 422
    
    if v.video_id in blacklist:
        return v.video_id, 403
    
    pos = songqueueing.push_queue(v)
    events.dispatch(songqueueing.QueuedSongEvent.new(pos, True, v))
    return str(pos), 200

@musicapi.post("/overlay/persistent")
@serve_when_loaded(web_loaded_callback)
def api_music_set_overlay_persistent():
    value = request.form.get("value", "false").strip().lower() == "true"
    events.dispatch(events.Event("songqueue:overlay_persistence_change", {"value": value}))
    return "", 200

@musicapi.post("/queue/skip")
@serve_when_loaded(web_loaded_callback)
def api_music_queue_skip():
    count_s = request.form.get("count", "1")
    purge_s = request.form.get("purge", "false").strip().lower().replace("false", "")
    npurge = not purge_s

    if not count_s.isdigit():
        return "Invalid count", 422
    count = int(count_s)
    pre_skipped = 0
    if count > 0:
        if songqueueing.current_song is not None:
            songqueueing.save_current_to_playlist = False
            if npurge:
                songqueueing.add_to_playlist(songqueueing.current_song.video_id)
            songqueueing.current_song = None
            #NOTE: cannot remove CURRENT_FILE here, as it is being used by the vlc player; current file is removed on its own during normal operation
            pre_skipped += 1
    else:
        return "0", 200, {"Content-Type": "application/json"}
    if count > 1:
        if songqueueing.next_song is not None:
            if npurge:
                songqueueing.add_to_playlist(songqueueing.next_song.video_id)
            songqueueing.next_song = None
            if os.path.isfile(songqueueing.NEXT_FILE):
                os.remove(songqueueing.NEXT_FILE)
            pre_skipped += 1
    elif pre_skipped: #count == 1 and current was skipped
        songqueueing.song_done.set()
        return "1", 200, {"Content-Type": "application/json"}

    with open(songqueueing.QUEUE_FILE, "r+") as f:
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
                    songqueueing.add_to_playlist(content[cutoff:space_index])
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
                    songqueueing.queue_populated.set()
                else:
                    songqueueing.queue_populated.clear()
            except:
                f.write(content)
                raise
            finally:
                songqueueing.song_done.set()
        else:
            songqueueing.song_done.set()
    return str(skip_count), 200, {"Content-Type": "application/json"}

@musicapi.route("/playerstate", methods=["GET", "POST"])
@serve_when_loaded(web_loaded_callback)
def api_music_playerstate():
    if songqueueing.current_song is None:
        rtv = "{\"state\": null}"
    else:
        if request.method == "POST":
            state = request.form["state"]
            if state == "play":
                songqueueing.vlc_player.play()
            elif state == "pause":
                songqueueing.vlc_player.pause()
            else:
                return "Invalid playerstate.", 422
            events.dispatch(events.Event("songqueue:change_playerstate", {
                "state": state,
                "position": songqueueing.vlc_player.get_position() * songqueueing.vlc_player.get_length()
            }))
        else:
            state = "play" if songqueueing.vlc_player.is_playing() else "pause"
        rtv = json.dumps({
            "state": state,
            "position": songqueueing.vlc_player.get_position() * songqueueing.vlc_player.get_length()
        })
    return rtv, 200, {"Content-Type": "application/json"}

@musicapi.post("/seek")
@serve_when_loaded(web_loaded_callback)
def api_musics_seek():
    if songqueueing.current_song is None:
        return
    seconds_s = request.form["seconds"]
    if not seconds_s.isdigit():
        return "Invalid seconds", 422
    seconds = float(seconds_s)
    if os.path.isfile(songqueueing.CURRENT_FILE):
        song = songqueueing.vlc_instance.media_new(songqueueing.CURRENT_FILE)
        song.add_option(f"start-time={seconds}")
        was_playing = songqueueing.vlc_player.is_playing()
        events.dispatch(events.Event("songqueue:change_playerstate", {
            "state": "play" if was_playing else "pause",
            "position": seconds * 1000
        }))
        songqueueing.vlc_player.set_media(song)
        if was_playing:
            songqueueing.vlc_player.play()
    return "", 200

@musicapi.route("/b-track", methods=["GET", "POST"])
@serve_when_loaded(web_loaded_callback)
def api_music_b_track():
    configs_parent = songqueueing.get_configs()
    configs:dict = configs_parent.get("Song-Queue", {})
    current_b_track:dict = configs.get("B-Track", None)
    index = songqueueing.b_track_index

    if request.method == "POST":
        url = request.form["url"].strip()
        if url:
            if current_b_track is None:
                btrack_config = {"url": url}
            else:
                btrack_config = {**current_b_track, "url": url}
            if "index" in request.form:
                index_s = request.form["index"]
                if not index_s.isdigit():
                    return "Invalid index", 422
                index = int(index_s)
                if index not in songqueueing.b_track_order:
                    index = songqueueing.b_track_index

            p = subprocess.Popen(["yt-dlp", url, "-I0", "-O", "playlist:playlist_count"], stdout=subprocess.PIPE)
            out, _ = p.communicate()
            if p.returncode:
                return "Failed to get playlist info.", 500
        
            raw_configs = config.read().get("Song-Queue")
            raw_configs["B-Track"] = btrack_config if url else None
            config.write(config_updates={
                "Song-Queue": raw_configs
            })
            songqueueing.b_track_playlist = url
            new_length = int(out)
            if new_length != songqueueing.b_track_length:
                songqueueing.b_track_order = list(range(1, new_length+1))
            songqueueing.b_track_length = new_length
            if current_b_track.get("random", False):
                random.shuffle(songqueueing.b_track_order)
            if index is None:
                songqueueing.b_track_index = 0
            else:
                songqueueing.b_track_index = songqueueing.b_track_order.index(index)
        else:
            raw_configs = config.read().get("Song-Queue")
            raw_configs["B-Track"] = None
            config.write(config_updates={
                "Song-Queue": raw_configs
            })
            songqueueing.b_track_playlist = songqueueing.b_track_index = songqueueing.b_track_length = songqueueing.b_track_order = None
    elif isinstance(current_b_track, dict) and current_b_track:
        url = current_b_track["url"]
    else:
        url = None

    return json.dumps({
        "url": url,
        "index": index
    }), 200, {"Content-Type": "application/json"}

@musicapi.get("/open-queue")
@serve_when_loaded(web_loaded_callback)
def api_music_open_queue():
    if os.path.isfile(songqueueing.QUEUE_FILE):
        os.startfile(songqueueing.QUEUE_FILE)
        return "", 200
    else:
        return "", 404
    
@musicapi.post("/blacklist")
@serve_when_loaded(web_loaded_callback)
def api_music_blacklist():
    id = request.form["id"]
    m = re.match(songqueueing.URL_REGEX, id)
    if m is not None:
        id = m[1]
    
    configs_parent = songqueueing.get_configs()
    c = configs_parent.get("Song-Queue", {})
    current_blacklist = c.get("Song-Blacklist", None)
    if isinstance(current_blacklist, list):
        if id not in current_blacklist:
            current_blacklist.append(id)
            updated = True
        else:
            updated = False
        
    else:
        current_blacklist = [id]
        updated = True
    
    if updated:
        raw_configs = config.read().get("Song-Queue")
        raw_configs["Song-Blacklist"] = current_blacklist
        config.write(config_updates={
            "Song-Queue": raw_configs
        })

    if songqueueing.current_song.video_id == id:
        songqueueing.current_song = None
        songqueueing.song_done.set()
    if songqueueing.next_song.video_id == id:
        songqueueing.next_song = None
    with open(songqueueing.QUEUE_FILE, "r+") as f:
        lines = [line for line in f if not line.startswith(id)]
        f.seek(0)
        f.truncate()
        if lines and lines[0].strip():
            f.write("\n".join(lines))
            songqueueing.queue_populated.set()
        else:
            songqueueing.queue_populated.clear()

    return "", 201

def _add_if_no_bp(t:Flask|Blueprint, bp:Blueprint):
    if isinstance(t, Flask):
        it = t.blueprints.values()
    else:
        it = (b for b, _ in t._blueprints)

    for b in it:
        if b == bp:
            return False
    t.register_blueprint(bp)
    return True

def add_routes(app:Flask, api:Blueprint):
    _add_if_no_bp(musicpages_parent, musicpages)
    _add_if_no_bp(app, musicpages_parent)
    _add_if_no_bp(api, musicapi)