import json
import requests
import time
import traceback
import vlc
import websocket

class SoundRequestPlayer:
    def __init__(self, api_url_host:str, api_secure:bool=False, output_device:str|None=None):
        self.vlc_instance:vlc.Instance = None
        self.vlc_player:vlc.MediaPlayer = None
        self.api_url_host = api_url_host
        self.api_secure = api_secure
        self.output_device = output_device
        self.wsa:websocket.WebSocketApp = None
    
    def load_sound(self, key:str):
        s = "s"*self.api_secure
        sound:vlc.Media = self.vlc_instance.media_new(f"http{s}://{self.api_url_host}/api/soundreq/sound/{key}")
        return sound
    
    def on_play_sound(self, event:dict[str]):
        key = event.get("key",None)
        if key is not None and event.get("success",True):
            sound = self.load_sound(key)
            self.vlc_player.set_media(sound)
            time.sleep(0.1)
            self.vlc_player.play()

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
    
    def _end_reached(self, _):
        s = "s"*self.api_secure
        requests.post(f"http{s}://{self.api_url_host}/api/soundreq/end")
    
    def ws_on_open(self, ws:websocket.WebSocket):
        self.init_vlc()
        if self.output_device is not None:
            device, _ = self.get_device(self.output_device)
            if device is not None:
                vlc.libvlc_audio_output_device_set(self.vlc_player, None, device)
        event_manager:vlc.EventManager = self.vlc_player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._end_reached)

    def ws_on_close(self, ws:websocket.WebSocket, status_code:int, msg:str|bytearray|memoryview):
        print(f"Sound request player connection closed ({status_code}):", msg)

    def ws_on_message(self, ws:websocket.WebSocket, msg:str|bytearray|memoryview):
        if isinstance(msg, memoryview):
            msg = msg.tobytes()
        data = json.loads(msg)
        if not isinstance(data, dict):
            return
        name = data.get("name", None)
        event = data.get("data", None)
        if not isinstance(event, dict):
            return
        if name == "soundreq:play_sound":
            self.on_play_sound(event)

    def ws_on_error(self, ws:websocket.WebSocket, e:Exception):
        traceback.print_exception(e)

    def start(self):
        s = "s"*self.api_secure
        self.wsa = websocket.WebSocketApp(f"ws{s}://{self.api_url_host}/api/events", on_open=self.ws_on_open, on_close=self.ws_on_close, on_message=self.ws_on_message, on_error=self.ws_on_error)
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