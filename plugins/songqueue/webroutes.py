from . import songqueueing
import config
from datetime import timedelta
import events
from flask import Blueprint, Flask, render_template, request, send_file, send_from_directory
import json
import os
import random
import re
import string
import subprocess
from web import add_bp_if_new, serve_when_loaded


DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(DIR, "static")
TEMPATES_DIR = os.path.join(DIR, "templates")

web_loaded = False
web_loaded_callback = lambda: web_loaded

musicpages_parent = Blueprint("musicparent", __name__, static_folder=STATIC_DIR, static_url_path="/static/music")
musicpages = Blueprint("music", __name__, url_prefix="/music", template_folder=TEMPATES_DIR)
musicoverlays = Blueprint("musicoverlay", __name__, url_prefix="/music/overlay", template_folder=TEMPATES_DIR)
musicapi = Blueprint("musicapi", __name__, url_prefix="/music")

@musicpages.get("/")
@serve_when_loaded(web_loaded_callback)
def music_interface():
    return render_template("music.html")

@musicoverlays.get("/")
@serve_when_loaded(web_loaded_callback)
def music_overlay():
    return render_template("music_overlay.html")

@musicapi.get("/thumbnail/<name>")
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
    with songqueueing.main_queue.open_queue() as f:
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
        "current": None if songqueueing.main_queue.current_song is None else _v_to_dict(songqueueing.main_queue.current_song),
        "next": None if songqueueing.main_queue.next_song is None else _v_to_dict(songqueueing.main_queue.next_song),
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
    
    pos = songqueueing.main_queue.push_queue(v)
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
    next_song_target = 1
    pre_skipped = 0
    if count > 0:
        if songqueueing.main_queue.current_song is None:
            next_song_target -= 1
        else:
            songqueueing.main_queue.save_current_to_playlist = False
            if npurge:
                songqueueing.add_to_playlist(songqueueing.main_queue.current_song.video_id)
            songqueueing.main_queue.current_song = None
            #NOTE: cannot remove CURRENT_FILE here, as it is being used by the vlc player; current file is removed on its own during normal operation
            pre_skipped += 1
    else:
        return "0", 200, {"Content-Type": "application/json"}
    
    if count > next_song_target:
        if songqueueing.main_queue.next_song is not None:
            if npurge:
                songqueueing.add_to_playlist(songqueueing.main_queue.next_song.video_id)
            if songqueueing.main_queue.song_loading_background is not None:
                songqueueing.main_queue.song_loading_background.kill()
                songqueueing.main_queue.song_loading_background.wait(0.5)
                songqueueing.main_queue.song_loading_background = None
            songqueueing.main_queue.next_song = None
            if os.path.isfile(songqueueing.main_queue.next_file):
                os.remove(songqueueing.main_queue.next_file)
            pre_skipped += 1
    elif pre_skipped: #count == 1 and current was skipped
        songqueueing.main_queue.current_tracker.end()
        return "1", 200, {"Content-Type": "application/json"}
    
    with songqueueing.main_queue.open_queue("r+") as f:
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
                    songqueueing.main_queue.queue_populated.set()
                else:
                    songqueueing.main_queue.queue_populated.clear()
            except:
                f.write(content)
                raise
            finally:
                songqueueing.main_queue.current_tracker.end()
        else:
            songqueueing.main_queue.current_tracker.end()
    return str(skip_count), 200, {"Content-Type": "application/json"}


@musicapi.route("/playerstate", methods=["GET", "POST"])
@serve_when_loaded(web_loaded_callback)
def api_music_playerstate():
    if songqueueing.main_queue.current_song is None:
        rtv = "{\"state\": null}"
    else:
        if request.method == "POST":
            state = request.form["state"]
            if state == "play":
                songqueueing.main_queue.current_tracker.play()
            elif state == "pause":
                songqueueing.main_queue.current_tracker.pause()
            else:
                return "Invalid playerstate.", 422
            events.dispatch(events.Event("songqueue:change_playerstate", {
                "state": state,
                "position": songqueueing.main_queue.current_tracker.get_elapsed() * 1000 #ms
            }))
        else:
            state = "play" if songqueueing.main_queue.current_tracker.is_playing() else "pause"
        rtv = json.dumps({
            "state": state,
            "position": songqueueing.main_queue.current_tracker.get_elapsed() * 1000 #ms
        })
    return rtv, 200, {
        "Content-Type": "application/json",
        "Song-Duration": songqueueing.format_duration(songqueueing.main_queue.current_tracker.duration)
    }

@musicapi.post("/seek")
@serve_when_loaded(web_loaded_callback)
def api_musics_seek():
    if songqueueing.main_queue.current_song is None:
        return
    seconds_s = request.form["seconds"]
    if not seconds_s.isdigit():
        return "Invalid seconds", 422
    seconds = float(seconds_s)
    if songqueueing.main_queue.current_song is not None:
        songqueueing.main_queue.current_tracker.set_elapsed(seconds)
        events.dispatch(events.Event("songqueue:change_playerstate", {
            "state": "play" if songqueueing.main_queue.current_tracker.is_playing() else "pause",
            "position": seconds * 1000
        }))
    return "", 200

@musicapi.route("/b-track", methods=["GET", "POST"])
@serve_when_loaded(web_loaded_callback)
def api_music_b_track():
    configs_parent = songqueueing.get_configs()
    configs:dict = configs_parent.get("Song-Queue", {})
    current_b_track:dict = configs.get("B-Track", None)
    index = songqueueing.main_queue.b_track_index

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
                if index not in songqueueing.main_queue.b_track_order:
                    index = songqueueing.main_queue.b_track_index

            p = subprocess.Popen(["yt-dlp", url, "-I0", "-O", "playlist:playlist_count"], stdout=subprocess.PIPE)
            out, _ = p.communicate()
            if p.returncode:
                return "Failed to get playlist info.", 500
        
            raw_configs = config.read().get("Song-Queue")
            raw_configs["B-Track"] = btrack_config if url else None
            config.write(config_updates={
                "Song-Queue": raw_configs
            })
            songqueueing.main_queue.b_track_playlist = url
            new_length = int(out)
            if new_length != songqueueing.main_queue.b_track_length:
                songqueueing.main_queue.b_track_order = list(range(1, new_length+1))
            songqueueing.main_queue.b_track_length = new_length
            if current_b_track.get("random", False):
                random.shuffle(songqueueing.main_queue.b_track_order)
            if index is None:
                songqueueing.main_queue.b_track_index = 0
            else:
                songqueueing.main_queue.b_track_index = songqueueing.main_queue.b_track_order.index(index)
        else:
            raw_configs = config.read().get("Song-Queue")
            raw_configs["B-Track"] = None
            config.write(config_updates={
                "Song-Queue": raw_configs
            })
            songqueueing.main_queue.b_track_playlist = songqueueing.main_queue.b_track_index = songqueueing.main_queue.b_track_length = songqueueing.main_queue.b_track_order = None
    elif isinstance(current_b_track, dict) and current_b_track:
        url = current_b_track["url"]
    else:
        url = None

    return json.dumps({
        "url": url,
        "index": index
    }), 200, {"Content-Type": "application/json"}

@musicapi.get("/song/current")
@serve_when_loaded(web_loaded_callback)
def api_music_song_current():
    if songqueueing.main_queue.current_song is not None and os.path.isfile(songqueueing.CURRENT_FILE):
        return send_file(songqueueing.CURRENT_FILE, conditional=True)
    return "", 404

@musicapi.get("/open-queue")
@serve_when_loaded(web_loaded_callback)
def api_music_open_queue():
    if os.path.isfile(songqueueing.main_queue.queue_file):
        os.startfile(songqueueing.main_queue.queue_file)
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
    c:dict = configs_parent.get("Song-Queue", {})
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

    if songqueueing.main_queue.current_song.video_id == id:
        songqueueing.main_queue.current_song = None
        songqueueing.main_queue.current_tracker.end()
    if songqueueing.main_queue.next_song.video_id == id:
        songqueueing.main_queue.next_song = None
    with songqueueing.main_queue.open_queue("r+") as f:
        lines = [line for line in f if not line.startswith(id)]
        f.seek(0)
        f.truncate()
        if lines and lines[0].strip():
            f.write("\n".join(lines))
            songqueueing.main_queue.queue_populated.set()
        else:
            songqueueing.main_queue.queue_populated.clear()

    return "", 201

def add_routes(app:Flask, api:Blueprint, add_interface=True, add_overlay=True, add_api=True):
    if add_interface:
        add_bp_if_new(musicpages_parent, musicpages)
    if add_overlay:
        add_bp_if_new(musicpages_parent, musicoverlays)
    if add_overlay or add_interface:
        add_bp_if_new(app, musicpages_parent)
    if add_api:
        add_bp_if_new(api, musicapi)