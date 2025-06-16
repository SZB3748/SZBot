from datetime import timedelta
import json
import requests
import threading
import time
import traceback
import vlc
import websocket

SongBounds = tuple[int, timedelta]

def parse_duration(s:str)->timedelta|None:
    duration_parts = s.split(":")
    if len(duration_parts) == 3:
        return timedelta(hours=int(duration_parts[0]), minutes=int(duration_parts[1]), seconds=int(duration_parts[2]))
    return None

class SongPlayer:
    def __init__(self, api_url_host:str, api_secure:bool=False, output_device:str=None):
        self.output_device = output_device
        self.vlc_instance:vlc.Instance = None
        self.vlc_player:vlc.MediaPlayer = None
        self.api_url_host = api_url_host # (website.name|1.2.3.4)(:port)?
        self.api_secure = api_secure
        self.wsa:websocket.WebSocketApp = None
        self.listeners = {
            "songqueue:play_song": [self.on_play_song],
            "songqueue:end_song": [self.on_end_song],
            "songqueue:change_playerstate": [self.on_change_playerstate]
        }
        self._current_song:SongBounds = None

    def load_current_song(self, start:int|float=None, duration:timedelta=None)->vlc.Media:
        s = "s"*self.api_secure
        if duration is None:
            duration = None if self._current_song is None else self._current_song[1]
        song:vlc.Media = self.vlc_instance.media_new(f"http{s}://{self.api_url_host}/api/music/song/current")
        if isinstance(start, (int,float)) and isinstance(duration, timedelta) and start < duration.total_seconds():
            song.add_option(f"start-time={start}")
        return song

    def on_play_song(self, data:dict[str]):
        if self.vlc_player.is_playing():
            self.vlc_player.pause()
            self.vlc_player.set_media(None)

        self._current_song = (data.get("start", 0), parse_duration(data.get("duration", None)))
        song = self.load_current_song(self._current_song[0])
        if song is not None:
            self.vlc_player.set_media(song)
            time.sleep(0.25)
            self.vlc_player.play()

    def on_end_song(self, data:dict[str]):
        if self.vlc_player.is_playing():
            self.vlc_player.pause()
        self.vlc_player.set_media(None)
        self._current_song = None

    def on_change_playerstate(self, data:dict[str]):
        state = data.get("state", None)
        position = data.get("position", None)
        if position is not None:
            song = self.load_current_song(position / 1000) #ms to s
            if song is not None:
                self.vlc_player.set_media(song)
        if state == "play":
            self.vlc_player.play()
        elif state == "pause":
            self.vlc_player.pause()

    def init_vlc(self):
        if self.vlc_instance is None:
            self.vlc_instance = vlc.Instance("--input-repeat=-1", "--fullscreen", "--file-caching=0")
        if self.vlc_player is None:
            self.vlc_player = self.vlc_instance.media_player_new()

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

    def load_late_current_song(self):
        s = "s"*self.api_secure
        start = time.time()
        r = requests.get(f"http{s}://{self.api_url_host}/api/music/playerstate")
        position = 0
        if r.ok:
            duration = parse_duration(r.headers.get("Song-Duration", ""))
            self._current_song = (0, duration)
            playerstate:dict[str] = r.json()
            position = playerstate.get("position",None)
            is_playing = bool(playerstate.get("state", None) == "play")
            if isinstance(position, (int,float)):
                end = time.time()
                position = position / 1000 - is_playing * (end - start)
            return self.load_current_song(position, duration), is_playing
        return None, None

    def ws_on_open(self, ws:websocket.WebSocket):
        self.init_vlc()
        if self.output_device is not None:
            device, _ = self.get_device(self.output_device)
            vlc.libvlc_audio_output_device_set(self.vlc_player, None, device)
        event_manager:vlc.EventManager = self.vlc_player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, lambda _: self.vlc_player.set_media(None))
        song_in_progress, is_playing = self.load_late_current_song()
        if song_in_progress is not None:
            self.vlc_player.set_media(song_in_progress)
            if is_playing:
                self.vlc_player.play()

    def ws_on_close(self, ws:websocket.WebSocket, status_code:int, msg:str|bytearray|memoryview):
        print(f"Songplayer connection closed ({status_code}):", msg)
        self.end()

    def ws_on_message(self, ws:websocket.WebSocket, msg:str|bytearray|memoryview):
        if isinstance(msg, memoryview):
            msg = msg.tobytes()
        event = json.loads(msg)
        if not isinstance(event, dict):
            return
        name = event.get("name",None)
        if not isinstance(name, str):
            return
        data = event.get("data",None)
        if not isinstance(data, dict):
            return
        cbs = self.listeners.get(name, None)
        if cbs is not None:
            for cb in cbs:
                cb(data)
        

    def ws_on_error(self, ws:websocket.WebSocket, e:Exception):
        traceback.print_exception(e)

    def start(self):
        s = "s"*self.api_secure
        self.wsa = websocket.WebSocketApp(f"ws{s}://{self.api_url_host}/api/events", on_open=self.ws_on_open, on_close=self.ws_on_close, on_message=self.ws_on_message, on_error=self.ws_on_error, )
        try:
            self.wsa.run_forever()
        except KeyboardInterrupt:
            pass

    def end(self):
        if self.wsa is not None:
            if self.wsa.keep_running:
                self.wsa.close()
            self.wsa = None
        if self.vlc_player is not None:
            if self.vlc_player.is_playing():
                self.vlc_player.pause()
            self.vlc_player.set_media(None)
            self.vlc_player = None

def run_song_player(player:SongPlayer, daemon:bool=False):
    t = threading.Thread(target=player.start, daemon=daemon)
    t.start()
    return t