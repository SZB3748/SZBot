from . import playlist
import config
from datetime import timedelta
import events
from io import TextIOWrapper
import os
import plugins
import random
import re
import string
import subprocess
import threading
import time
from types import TracebackType
from typing import MutableSequence
import vlc

THUMBNAILS_DIR = "thumbnails"
CURRENT_FILE = "CURRENT"
NEXT_FILE = "NEXT"
QUEUE_FILE = "QUEUE"
URL_REGEX = re.compile(r"^(?:http(?:s)?:\/\/(?:www\.)?)?youtu(?:be\.com\/watch\?v=|\.be\/)([\w\-\_]*)(&(amp;)?[\w\?=]*)?")
T_PARAM_REGEX = re.compile(r"^.*?\?.*?&?t=(?:([0-9]+)h)?(?:([0-9]+)m)(?:([0-9]+)(?:s)?)?(?:&|$)")
THUMBNAIL_OUTPUT_REGEX = re.compile(r"\[info\] Writing video thumbnail .*? to: .*?[\\/](.*?)(?:\r|\n|$)")

youtube_api = None
meta:plugins.Meta = None

def get_configs():
    if meta is None:
        return config.read(path=config.CONFIG_FILE)
    return plugins.read_configs(path=config.CONFIG_FILE, meta=meta)

class _QueueFileContextHandler:
    def __init__(self, lock:threading.Lock, file:TextIOWrapper):
        self.lock = lock
        self.file:TextIOWrapper = file

    def __enter__(self)->TextIOWrapper:
        self.lock.__enter__()
        return self.file.__enter__()

    def __exit__(self, type:type[BaseException], value:BaseException, tb:TracebackType):
        if self.file is not None:
            self.file.__exit__(type, value, tb)
        self.lock.__exit__(type, value, tb)


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
    event_name = "songqueue:queue_song"

    @classmethod
    def new(cls, pos:int, success:bool, v:QueuedSong):
        return cls(pos=pos, success=success, video_id=v.video_id, title=v.title, duration=v.duration, thumbnail=v.thumbnail, start=v.start, b_track=v.b_track)

    def __init__(self, pos:int, success:bool, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data.update(pos=pos, success=success)

class PlaySongEvent(QueueDataEvent):
    event_name = "songqueue:play_song"

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

def add_to_playlist(video_id:str):
    """Add to the youtube playlist if one is specified in config.json"""
    configs_parent = get_configs()
    configs:dict = configs_parent.get("Song-Queue", {})
    if "Playlist" in configs:
        return playlist.add_video(youtube_api, configs["Playlist"], video_id)
    
def get_playlist_song(url:str, number:str)->QueuedSong|None:
    idP = subprocess.Popen(["yt-dlp", url, "--playlist-start="+str(number), "--playlist-end="+str(number), "--print", "%(id)s"], stdout=subprocess.PIPE)
    out_id, _ = idP.communicate()
    if not idP.returncode:
        return get_song(f"https://youtube.com/watch?v={out_id.decode("utf-8").strip()}")
    else:
        print(f"Failed to get video ID for playlist video #{number}")

class SongQueue:
    """Class that handles waiting for songs in a queue file and playing them through a vlc instance."""
    def __init__(self, queue_file:str=QUEUE_FILE, current_file:str=CURRENT_FILE, next_file:str=NEXT_FILE):
        self.stop_loop = threading.Event()
        self.song_done = threading.Event()
        self.queue_populated = threading.Event()
        self.queue_lock = threading.Lock()
        self.queue_file = queue_file
        self.current_file = current_file
        self.next_file = next_file
        self.vlc_instance:vlc.Instance = None
        self.vlc_player:vlc.MediaPlayer = None
        self.b_track_is_current:bool = False
        self.b_track_is_next:bool = False
        self.save_current_to_playlist:bool = True
        self.next_song:QueuedSong = None
        self.current_song:QueuedSong = None
        self.b_track_playlist:str = None
        self.b_track_index:int = None
        self.b_track_length:int = None
        self.b_track_order:MutableSequence[int] = None

    def init_vlc(self):
        if self.vlc_instance is None:
            self.vlc_instance = vlc.Instance("--input-repeat=-1", "--fullscreen", "--file-caching=0")
        if self.vlc_player is None:
            self.vlc_player = self.vlc_instance.media_player_new()

    def open_queue(self, mode:str="r", buffering:int=-1, encoding:str|None=None, errors:str|None=None, newline:str|None=None, closefd:bool=True, opener=None, *args, **kwargs):
        """Allows for the queue lock to be aquired and the queue file to be opened in the same `with` statement."""
        return _QueueFileContextHandler(self.queue_lock, open(self.queue_file, mode, buffering, encoding, errors, newline, closefd, opener, *args, **kwargs))

    #cite: https://stackoverflow.com/a/73886462
    def get_device(self, name:str):
        mods = self.vlc_player.audio_output_device_enum()
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

    def push_queue(self, *vs:QueuedSong)->int:
        with self.open_queue("a+") as f:
            for v in vs:
                f.write(v.to_str())
                f.write("\n")
            f.seek(0)
            count = f.read().count("\n")
        self.queue_populated.set()
        #add to count if NEXT is present to include the preloaded song in the queue, and subtract from count if there is no CURRENT (song will be moving up)
        return count + os.path.isfile(self.next_file) - (not os.path.isfile(self.current_song))

    def pop_queue(self)->QueuedSong|None:
        with self.open_queue("r+") as f:
            contents = f.read().strip()
            if not contents:
                self.queue_populated.clear()
                return
            nl_index = contents.find("\n")
            f.seek(0)
            f.truncate()
            try:
                if nl_index < 0:
                    old_contents = contents
                    self.queue_populated.clear()
                else:
                    old_contents = contents[:nl_index]
                    new_contents  = contents[nl_index+1:]
                    if any(c not in string.whitespace for c in new_contents):
                        f.write(new_contents)
                        self.queue_populated.set()
                    else:
                        self.queue_populated.clear()
                id, duration_s, thumbnail, start_s, title = old_contents.split(" ", 4)
                duration = parse_duration(duration_s)
                if duration is not None:
                    return QueuedSong(id, title.strip(), duration, thumbnail, start=int(start_s))
            except:
                f.write(contents)
                raise

    def get_next_song(self)->QueuedSong|None:
        configs_parent = get_configs()
        configs:dict = configs_parent.get("Song-Queue", {})

        current_btrack = None
        current_index = None
        if "B-Track" in configs:
            btrack_settings = configs["B-Track"]
            if isinstance(btrack_settings, dict) and "url" in btrack_settings:
                current_btrack = btrack_settings["url"]
                current_index = btrack_settings.get("start", None)
                if current_index is not None:
                    if isinstance(current_index, float):
                        current_index = int(current_index)
                    if current_index < 1:
                        current_index = 1
                if self.b_track_playlist != current_btrack:
                    p = subprocess.Popen(["yt-dlp", current_btrack, "-I0", "-O", "playlist:playlist_count"], stdout=subprocess.PIPE)
                    out, _ = p.communicate()
                    if p.returncode:
                        print("Failed to get playlist info")
                        self.b_track_playlist = None
                        self.b_track_index = None
                        self.b_track_length = None
                        self.b_track_order = None
                    else:
                        self.b_track_playlist = current_btrack
                        self.b_track_length = int(out)
                        self.b_track_order = list(range(1, self.b_track_length+1))
                        if btrack_settings.get("random", False):
                            random.shuffle(self.b_track_order)
                        if current_index is not None and current_index in self.b_track_order:
                            self.b_track_index = self.b_track_order.index(current_index)
                        else:
                            self.b_track_index = 0

        if isinstance(self.b_track_playlist, str):
            with self.open_queue() as f:
                contents = f.read()

            if any(c not in string.whitespace for c in contents):
                self.queue_populated.set()
                if self.b_track_is_next:
                    self.next_song = None
                    if os.path.isfile(self.next_file):
                        os.remove(self.next_file)
                self.b_track_is_next = False
            else:
                self.queue_populated.clear()
                self.b_track_is_next = True
                playlist_index = self.b_track_order[self.b_track_index]
                v = get_playlist_song(self.b_track_playlist, playlist_index)
                if v is None:
                    events.dispatch(QueuedSongEvent(-1, False, video_id=f"{self.b_track_playlist}&index={playlist_index}", title="", duration=timedelta(seconds=0), thumbnail="", start=0, b_track=True))
                else:
                    v.b_track = True
                    events.dispatch(QueuedSongEvent.new(1, True, v))
                return v
        else:
            self.b_track_playlist = self.b_track_index = self.b_track_length = self.b_track_order = None
            if self.b_track_is_next and os.path.isfile(self.next_file):
                os.remove(self.next_file)
            self.b_track_is_next = False

        return self.pop_queue()

    def increment_b_track(self, delta:int=1):
        self.b_track_index = (self.b_track_index + delta) % self.b_track_length
        return self.b_track_index

    def load_next_bg(self):
        try:
            self.next_song = self.get_next_song()
            if self.next_song is not None:
                download_song(self.next_song.url, self.next_file)
        except KeyboardInterrupt:
            pass

    def ready_song(self):
        if self.b_track_is_next:
            with self.open_queue() as f:
                contents = f.read()
            if any(c not in string.whitespace for c in contents):
                self.queue_populated.set()
                if self.b_track_is_next:
                    self.next_song = None
                    if os.path.isfile(self.next_file):
                        os.remove(self.next_file)
                self.b_track_is_next = False
            else:
                self.queue_populated.clear()

        if self.current_song is None:
            if self.next_song is None:
                v = self.get_next_song()
                if not v:
                    if self.b_track_is_next:
                        self.increment_b_track()
                    return
                s = download_song(v.url, file=self.current_file)
                self.current_song = v
                if s.wait():
                    self.current_song = None
                elif self.b_track_is_next:
                    self.increment_b_track()
            else:
                self.current_song = self.next_song
                self.next_song = None
                if os.path.isfile(self.current_file):
                    os.remove(self.current_file)
                if os.path.isfile(self.next_file):
                    os.rename(self.next_file, self.current_file)
                if self.b_track_is_next:
                    self.increment_b_track()
            
        if self.next_song is None:
            threading.Thread(target=self.load_next_bg, daemon=True).start()

    def song_cycle(self):
        self.init_vlc()

        configs_parent = get_configs()
        configs:dict = configs_parent.get("Song-Queue", {})

        if "Output-Device" in configs:
            device, _ = self.get_device(configs["Output-Device"])
            vlc.libvlc_audio_output_device_set(self.vlc_player, None, device)
        
        event_manager:vlc.EventManager = self.vlc_player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, lambda _: self.song_done.set())

        if not os.path.isdir(THUMBNAILS_DIR):
            os.mkdir(THUMBNAILS_DIR)
        if not os.path.isfile(self.queue_file):
            open(self.queue_file, "x").close()
        if os.path.isfile(self.current_file):
            os.remove(self.current_file)
        if os.path.isfile(self.next_file):
            os.remove(self.next_file)

        print("Handling song queue")

        try:
            while not self.stop_loop.is_set():
                if self.queue_populated.wait(3.0):
                    print("Getting next song")
                if self.stop_loop.is_set():
                    return
                self.ready_song()

                if self.stop_loop.is_set():
                    return
                if self.current_song and os.path.isfile(self.current_file):
                    cs = self.current_song #keep a reference to the object in case the global reference is changed
                    self.b_track_is_current = self.b_track_is_next
                    
                    song:vlc.Media = self.vlc_instance.media_new(self.current_file)
                    if self.current_song.start and self.current_song.start < self.current_song.duration.total_seconds():
                        song.add_option(f"start-time={self.current_song.start}")
                    self.vlc_player.set_media(song)

                    time.sleep(0.25)
                    if self.stop_loop.is_set():
                        return

                    self.song_done.clear()
                    print(f"Playing Song: [{self.current_song.video_id}] ({self.current_song.duration}) {self.current_song.title}")
                    self.vlc_player.play()
                    events.dispatch(PlaySongEvent.new(self.current_song))

                    self.song_done.wait()

                    if self.vlc_player.is_playing():
                        print("Stopping", cs.video_id)
                        self.vlc_player.pause()

                    print("Stopped", cs.video_id)
                    self.vlc_player.set_media(None)
                    os.remove(self.current_file)

                    if self.save_current_to_playlist:
                        r = add_to_playlist(cs.video_id)
                        if r:
                            print(r) #youtube data api response
                    else:
                        self.save_current_to_playlist = True
                    self.current_song = None
                else:
                    self.b_track_is_current = False
        except KeyboardInterrupt:
            pass
        finally:
            if self.vlc_player.get_media() is not None:
                self.vlc_player.pause()
            self.vlc_player.set_media(None)

def run_song_cycle(queue:SongQueue, daemon:bool=False):
    queue.stop_loop.clear()
    queue.song_done.clear()
    t = threading.Thread(target=queue.song_cycle, daemon=daemon)
    t.start()
    return t


main_queue:SongQueue = None
