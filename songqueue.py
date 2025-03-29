import config
from datetime import timedelta
import events
import os
import playlist
import random
import re
import string
import subprocess
import threading
import time
from typing import MutableSequence
import vlc

THUMBNAILS_DIR = "thumbnails"
CURRENT_FILE = "CURRENT"
NEXT_FILE = "NEXT"
QUEUE_FILE = "QUEUE"
URL_REGEX = re.compile(r"^(?:http(?:s)?:\/\/(?:www\.)?)?youtu(?:be\.com\/watch\?v=|\.be\/)([\w\-\_]*)(&(amp;)?[\w\?=]*)?")
T_PARAM_REGEX = re.compile(r"^.*?\?.*?&?t=(?:([0-9]+)h)?(?:([0-9]+)m)(?:([0-9]+)(?:s)?)?(?:&|$)")
THUMBNAIL_OUTPUT_REGEX = re.compile(r"\[info\] Writing video thumbnail .*? to: .*?[\\/](.*?)(?:\r|\n|$)")

stop_loop = threading.Event()
song_done = threading.Event()
queue_populated = threading.Event()
queue_push_lock = threading.Lock()
b_track_is_current = False
b_track_is_next = False
save_current_to_playlist = True

vlc_instance = vlc.Instance("--input-repeat=-1", "--fullscreen", "--file-caching=0")
vlc_player = vlc_instance.media_player_new()

youtube_api = playlist.get_authenticated_service()

class QueuedSong:
    "A song gotten from a youtube video that is/was queued."
    def __init__(self, video_id:str, title:str, duration:timedelta, thumbnail:str, start:int=0, b_track:bool=False):
        self.video_id = video_id
        self.title = title
        self.duration = duration
        self.thumbnail = thumbnail
        self.start = start
        self.b_track = b_track

    @property
    def url(self):
        return f"https://youtube.com/watch?v={self.video_id}"
    
    def to_str(self)->str:
        return f"{self.video_id} {format_duration(self.duration)} {self.thumbnail} {self.start} {self.title}"

class QueueDataEvent(events.Event):
    """An event that passes around QueuedSong data."""

    event_name:str = None

    @classmethod
    def new(cls, v:QueuedSong):
        return cls(
            video_id=v.video_id,
            title=v.title,
            duration=v.duration,
            thumbnail=v.thumbnail,
            start=v.start,
            b_track=v.b_track
        )

    def __init__(self, video_id:str, title:str, duration:timedelta, thumbnail:str, start:int, b_track:bool):
        super().__init__(self.event_name, {
            "id": video_id,
            "title": title,
            "duration": format_duration(duration),
            "thumbnail": thumbnail,
            "start": start,
            "b_track": b_track
        })


class QueuedSongEvent(QueueDataEvent):
    event_name = "queue_song"

    @classmethod
    def new(cls, pos:int, success:bool, v:QueuedSong):
        return cls(pos=pos, success=success, video_id=v.video_id, title=v.title, duration=v.duration, thumbnail=v.thumbnail, start=v.start, b_track=v.b_track)

    def __init__(self, pos:int, success:bool, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data.update(pos=pos, success=success)

class PlaySongEvent(QueueDataEvent):
    event_name = "play_song"


next_song:QueuedSong = None
current_song:QueuedSong = None
b_track_playlist:str = None
b_track_index:int = None
b_track_length:int = None
b_track_order:MutableSequence[int] = None

#cite: https://stackoverflow.com/a/73886462
def get_device(name:str):
    mods = vlc_player.audio_output_device_enum()
    if mods:
        mod = mods
        while mod:
            mod = mod.contents
            if name in str(mod.description):
                vlc.libvlc_audio_output_device_list_release(mods)
                return mod.device, mod.description
            mod = mod.next
        vlc.libvlc_audio_output_device_list_release(mods)
    return None, None

def parse_duration(s:str)->timedelta|None:
    duration_parts = s.split(":")
    if len(duration_parts) == 3:
        return timedelta(hours=int(duration_parts[0]), minutes=int(duration_parts[1]), seconds=int(duration_parts[2]))
    return None

def format_duration(td:timedelta)->str:
    hours = str(int(td.total_seconds() // 3600)).rjust(2, "0")
    mins = str(int(td.total_seconds() // 60) % 60).rjust(2, "0")
    secs = str(int(td.total_seconds()) % 60).rjust(2, "0")
    return ":".join([hours, mins, secs])

def push_queue(*vs:QueuedSong)->int:
    with queue_push_lock:
        with open(QUEUE_FILE, "a+") as f:
            for v in vs:
                f.write(v.to_str())
                f.write("\n")
            f.seek(0)
            count = f.read().count("\n")
        queue_populated.set()
    #add to count if NEXT is present to include the preloaded song in the queue, and subtract from count if there is no CURRENT (song will be moving up)
    return count + os.path.isfile(NEXT_FILE) - (not os.path.isfile(CURRENT_FILE))

def pop_queue()->QueuedSong|None:
    with open(QUEUE_FILE, "r+") as f:
        contents = f.read().strip()
        if not contents:
            queue_populated.clear()
            return
        nl_index = contents.find("\n")
        f.seek(0)
        f.truncate()
        try:
            if nl_index < 0:
                old_contents = contents
                queue_populated.clear()
            else:
                old_contents = contents[:nl_index]
                new_contents  = contents[nl_index+1:]
                if any(c not in string.whitespace for c in new_contents):
                    f.write(new_contents)
                    queue_populated.set()
                else:
                    queue_populated.clear()
            id, duration_s, thumbnail, start_s, title = old_contents.split(" ", 4)
            duration = parse_duration(duration_s)
            if duration is not None:
                return QueuedSong(id, title.strip(), duration, thumbnail, start=int(start_s))
        except:
            f.write(contents)
            raise

def get_next_song()->QueuedSong|None:
    global b_track_playlist, b_track_is_next, b_track_index, b_track_length, b_track_order, next_song
    configs = config.read()

    current_btrack = None
    current_index = None
    if "B-Track" in configs:
        btrack_settings = configs["B-Track"]
        if isinstance(btrack_settings, dict) and "url" in btrack_settings:
            current_btrack = btrack_settings["url"]
            current_index = btrack_settings.get("start", None)
            if current_index is not None:
                if isinstance(current_index, float):
                    current_index = min(1, int(current_index))
                elif not (isinstance(current_index, int) and current_index > 0):
                    current_index = int(current_index)
            if b_track_playlist != current_btrack:
                p = subprocess.Popen(["yt-dlp", current_btrack, "-I0", "-O", "playlist:playlist_count"], stdout=subprocess.PIPE)
                out, _ = p.communicate()
                if p.returncode:
                    print("Failed to get playlist info")
                    b_track_playlist = None
                    b_track_index = None
                    b_track_length = None
                    b_track_order = None
                else:
                    b_track_playlist = current_btrack
                    b_track_length = int(out)
                    b_track_order = list(range(1, b_track_length+1))
                    if btrack_settings.get("random", False):
                        random.shuffle(b_track_order)
                    if current_index is not None and current_index in b_track_order:
                        b_track_index = b_track_order.index(current_index)
                    else:
                        b_track_index = 0

    if isinstance(b_track_playlist, str):
        with open(QUEUE_FILE) as f:
            contents = f.read()

        if any(c not in string.whitespace for c in contents):
            queue_populated.set()
            if b_track_is_next:
                next_song = None
                if os.path.isfile(NEXT_FILE):
                    os.remove(NEXT_FILE)
            b_track_is_next = False
        else:
            queue_populated.clear()
            b_track_is_next = True
            playlist_index = b_track_order[b_track_index]
            v = get_playlist_song(b_track_playlist, playlist_index)
            v.b_track = True
            if v is None:
                events.dispatch(QueuedSongEvent(-1, False, video_id=f"{b_track_playlist}&index={playlist_index}", title="", duration=timedelta(seconds=0), thumbnail="", start=0, b_track=True))
            else:
                events.dispatch(QueuedSongEvent.new(1, True, v))
            return v
    else:
        b_track_playlist = b_track_index = b_track_length = b_track_order = None
        if b_track_is_next and os.path.isfile(NEXT_FILE):
            os.remove(NEXT_FILE)
        b_track_is_next = False

    return pop_queue()

def add_to_playlist(video_id:str):
    """Add to the youtube playlist if one is specified in config.json"""
    configs = config.read()
    if "Playlist" in configs:
        return playlist.add_video(youtube_api, configs["Playlist"], video_id)

def get_playlist_song(url:str, number:str)->QueuedSong|None:
    idP = subprocess.Popen(["yt-dlp", url, "--playlist-start="+str(number), "--playlist-end="+str(number), "--print", "%(id)s"], stdout=subprocess.PIPE)
    out_id, _ = idP.communicate()
    if not idP.returncode:
        return get_song(f"https://youtube.com/watch?v={out_id.decode("utf-8").strip()}")
    else:
        print(f"Failed to get video ID for playlist video #{number}")

def increment_b_track(delta:int=1):
    global b_track_index
    b_track_index = (b_track_index + delta) % b_track_length
    return b_track_index

def get_song(url:str)->QueuedSong|None:
    m = re.match(URL_REGEX, url)
    id = None if m is None else m[1] or None
    if id is None:
        print("Invalid URL:", url)
        return
    infoP = subprocess.Popen(["yt-dlp", url, "--print", "%(duration>%H:%M:%S)s %(title)s"], stdout=subprocess.PIPE)
    thumbnailP = subprocess.Popen(["yt-dlp", "--write-thumbnail", "--skip-download", url, "-o", os.path.join(THUMBNAILS_DIR, id)], stdout=subprocess.PIPE)
    out_info, _ = infoP.communicate()
    out_thumbnail, _ = thumbnailP.communicate()
    if infoP.returncode:
        print("Failed to get video info: code", infoP.returncode)
    elif thumbnailP.returncode:
        print("Failed to get video thumbnail: code", thumbnailP.returncode)
    else:
        m = re.search(THUMBNAIL_OUTPUT_REGEX, out_thumbnail.decode("utf-8"))
        thumbnail = None if m is None else m[1] or None
        if thumbnail is None:
            print("Could not identify thumbnail file")
            return
        
        duration_s, title = out_info.decode("utf-8").split(" ", 1)
        duration = parse_duration(duration_s)
        if duration is not None:
            start_m = re.match(T_PARAM_REGEX, url)
            start = 0
            if start_m:
                hours = start_m[1]
                minutes = start_m[2]
                seconds = start_m[3]
                if hours is not None:
                    start += int(hours) * 3600
                if minutes is not None:
                    start += int(minutes) * 60
                if seconds is not None:
                    start += int(seconds)
            return QueuedSong(id, title.strip(), duration, thumbnail, start=start)

        print("Invalid duration format:", duration_s)

def download_song(url:str, file:str=NEXT_FILE)->subprocess.Popen:
    print(f"Starting download into {file}: {url}")
    if os.path.isfile(file):
        os.remove(file)
    return subprocess.Popen(["yt-dlp", "--ignore-errors", "-f", "bestaudio", url, "-o", file])

def load_next_bg():
    global next_song
    next_song = get_next_song()
    if next_song is not None:
        download_song(next_song.url)

def ready_song():
    global current_song, next_song, b_track_is_next

    if b_track_is_next:
        with open(QUEUE_FILE) as f:
            contents = f.read()
        if any(c not in string.whitespace for c in contents):
            queue_populated.set()
            if b_track_is_next:
                next_song = None
                if os.path.isfile(NEXT_FILE):
                    os.remove(NEXT_FILE)
            b_track_is_next = False
        else:
            queue_populated.clear()

    if current_song is None:
        if next_song is None:
            v = get_next_song()
            if not v:
                return
            s = download_song(v.url, file=CURRENT_FILE)
            current_song = v
            if s.wait():
                current_song = None
            elif b_track_is_next:
                increment_b_track()
        else:
            current_song = next_song
            next_song = None
            if os.path.isfile(CURRENT_FILE):
                os.remove(CURRENT_FILE)
            if os.path.isfile(NEXT_FILE):
                os.rename(NEXT_FILE, CURRENT_FILE)
            if b_track_is_next:
                increment_b_track()
        
    if next_song is None:
        threading.Thread(target=load_next_bg).start()

def song_cycle():
    global current_song, b_track_is_current, save_current_to_playlist

    configs = config.read()
    if "Output-Device" in configs:
        device, _ = get_device(configs["Output-Device"])
        vlc.libvlc_audio_output_device_set(vlc_player, None, device)
    
    event_manager = vlc_player.event_manager()
    event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, lambda _: song_done.set())

    if not os.path.isdir(THUMBNAILS_DIR):
        os.mkdir(THUMBNAILS_DIR)
    if not os.path.isfile(QUEUE_FILE):
        open(QUEUE_FILE, "x").close()
    if os.path.isfile(CURRENT_FILE):
        os.remove(CURRENT_FILE)
    if os.path.isfile(NEXT_FILE):
        os.remove(NEXT_FILE)

    print("Handling song queue")

    while not stop_loop.is_set():
        if queue_populated.wait(3.0):
            print("Getting next song")
        if stop_loop.is_set():
            return
        ready_song()

        if stop_loop.is_set():
            return
        if current_song and os.path.isfile(CURRENT_FILE):
            cs = current_song #keep a reference to the object in case the global reference is changed
            b_track_is_current = b_track_is_next
            
            song = vlc_instance.media_new(CURRENT_FILE)
            if current_song.start and current_song.start < current_song.duration.total_seconds():
                song.add_option(f"start-time={current_song.start}")
            vlc_player.set_media(song)

            time.sleep(0.25)

            song_done.clear()
            print(f"Playing: [{current_song.video_id}] ({current_song.duration}) {current_song.title}")
            vlc_player.play()
            events.dispatch(PlaySongEvent.new(current_song))

            song_done.wait()

            if vlc_player.is_playing():
                print("Stopping", cs.video_id)
                vlc_player.pause()

            print("Stopped", cs.video_id)
            vlc_player.set_media(None)
            os.remove(CURRENT_FILE)

            if save_current_to_playlist:
                r = add_to_playlist(cs.video_id)
                if r:
                    print(r)
            else:
                save_current_to_playlist = True
            current_song = None
        else:
            b_track_is_current = False
        # time.sleep(1)

def run_song_cycle():
    t = threading.Thread(target=song_cycle)
    t.start()
    return t

