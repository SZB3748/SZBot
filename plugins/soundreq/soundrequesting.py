import config
import events
import json
import os
import plugins
import threading
import time
import traceback
import vlc
import websocket

queue_lock = threading.Lock()
queue:list[tuple[str, str|None, str|None]] = []
queue_handler:threading.Thread = None
sound_done = threading.Event()

meta:plugins.Meta = None

def get_configs():
    if meta is None:
        return config.read(path=config.CONFIG_FILE)
    return plugins.read_configs(path=config.CONFIG_FILE, meta=meta)

def get_sound(key:str)->dict[str]|None:
    config_parent = get_configs()
    configs:dict = config_parent.get("Sound-Request", {})
    if "Sounds" in configs:
        sounds:dict[str] = configs["Sounds"]
        return sounds.get(key, None)

def add_queue(key:str, user:str|None=None, channel:str|None=None):
    with queue_lock:
        queue.append((key, user, channel))

def popall_queue():
    with queue_lock:
        if not queue:
            return None
        rtv = queue.copy()
        queue.clear()
    return rtv

def _format_request_origin(user:str|None, channel:str|None):
    if channel:
        return f" from {user}@{channel}"
    elif user:
        return f" from {user}"
    else:
        return ""

def handler_target(sound_keys:list[tuple[str, str|None, str|None]]=None):
    global queue_handler

    if not sound_keys:
        sound_keys = popall_queue()

    while queue_handler and sound_keys:
        for key, user, channel in sound_keys:
            print(f"Sound Request{_format_request_origin(user, channel)}: {key} ")
            info = get_sound(key)
            if info is None:
                print("Sound does not exist")
                continue
            filepath = info["file"]
            if not os.path.isfile(filepath):
                print("Sound has no file")
                continue
        
            if queue_handler is None:
                return
            
            sound_done.clear()
            print("Playing Sound", key)
            events.dispatch(events.Event("soundreq:play_sound", {"success": True, "key":key, "sound": info}))

            sound_done.wait()
            
            print("Stopped Sound", key)

            if queue_handler is None:
                return

        sound_keys = popall_queue()
    
    queue_handler = None

def invoke_handler():
    global queue_handler
    if queue_handler is None:
        queue_handler = threading.Thread(target=handler_target, args=(popall_queue(),), daemon=True)
        queue_handler.start()


class SoundRequestPlayer:
    def __init__(self, api_url_host:str, api_secure:bool=False):
        self.vlc_instance:vlc.Instance = None
        self.vlc_player:vlc.MediaPlayer = None
        self.api_url_host = api_url_host
        self.api_secure = api_secure
        self.wsa:websocket.WebSocketApp = None
        self.listeners = events.EventListenerCollection({
            "soundreq:play_sound": [events.EventListener(self.on_play_sound)]
        })
    
    def load_sound(self, key:str):
        s = "s"*self.api_secure
        sound:vlc.Media = self.vlc_instance.media_new(f"http{s}://{self.api_url_host}/api/soundreq/sound/{key}")
        return sound
    
    def on_play_sound(self, event:events.Event):
        key = event.data.get("key",None)
        if key is not None and event.data.get("success",True):
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
    
    def ws_on_open(self, ws:websocket.WebSocket):
        self.init_vlc()
        configs_parent = get_configs()
        configs:dict = configs_parent.get("Sound-Request", {})
        if "Output-Device" in configs:
            device, _ = self.get_device(configs["Output-Device"])
            vlc.libvlc_audio_output_device_set(self.vlc_player, None, device)
        event_manager = self.vlc_player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, lambda _: self.vlc_player.set_media(None))

    def ws_on_close(self, ws:websocket.WebSocket, status_code:int, msg:str|bytearray|memoryview):
        print(f"Sound request player connection closed ({status_code}):", msg)

    def ws_on_message(self, ws:websocket.WebSocket, msg:str|bytearray|memoryview):
        if isinstance(msg, memoryview):
            msg = msg.tobytes()
        data = json.loads(msg)
        event = events.Event(**data)
        self.listeners.handle_event(event)

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
