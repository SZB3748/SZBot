import config
import events
import os
import plugins
import threading

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
