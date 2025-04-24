import config
import events
import os
import plugins
import threading
import time
import vlc

SOUNDS_DIR = "sounds"

queue_lock = threading.Lock()
queue:list[str] = []
queue_handler:threading.Thread = None
sound_done = threading.Event()

vlc_instance = vlc.Instance("--input-repeat=-1", "--fullscreen", "--file-caching=0")
vlc_player = vlc_instance.media_player_new()

meta:plugins.Meta = None

def get_configs():
    if meta is None:
        return config.read(path=config.CONFIG_FILE)
    return plugins.read_configs(path=config.CONFIG_FILE, meta=meta)

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

def get_sound(key:str)->dict[str]|None:
    config_parent = get_configs()
    configs:dict = config_parent.get("Sound-Request", {})
    if "Sounds" in configs:
        sounds:dict[str] = configs["Sounds"]
        return sounds.get(key, None)

def add_queue(key:str):
    with queue_lock:
        queue.append(key)

def popall_queue()->list[str]|None:
    with queue_lock:
        if not queue:
            return None
        rtv = queue.copy()
        queue.clear()
    return rtv

def init():
    configs_parent = get_configs()
    configs:dict = configs_parent.get("Sound-Request", {})
    if "Output-Device" in configs:
        device, _ = get_device(configs["Output-Device"])
        vlc.libvlc_audio_output_device_set(vlc_player, None, device)
    
    event_manager = vlc_player.event_manager()
    event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, lambda _: sound_done.set())


def handler_target(sound_keys:list[str]=None):
    global queue_handler

    if not sound_keys:
        sound_keys = popall_queue()

    while queue_handler and sound_keys:
        for key in sound_keys:
            info = get_sound(key)
            if info is None:
                print("Sound does not exist:", key)
                continue
            filepath = info["file"]
            if not os.path.isfile(filepath):
                print("Sound has no file:", key)
                continue
            sound = vlc_instance.media_new(filepath)
            vlc_player.set_media(sound)
        
            time.sleep(0.1)
            if queue_handler is None:
                return
            
            sound_done.clear()
            print("Playing Sound:", key)
            vlc_player.play()
            events.dispatch(events.Event("soundreq:play_sound", {"success": True, "sound": info}))

            sound_done.wait()

            if vlc_player.is_playing():
                print("Stopping Sound", key)
            
            print("Stopped Sound", key)
            vlc_player.set_media(None)

            if queue_handler is None:
                return

        sound_keys = popall_queue()
    
    queue_handler = None

def invoke_handler():
    global queue_handler
    if queue_handler is None:
        queue_handler = threading.Thread(target=handler_target, args=(popall_queue(),), daemon=True)
        queue_handler.start()