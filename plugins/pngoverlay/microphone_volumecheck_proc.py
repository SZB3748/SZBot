import asyncio
import json
import queue
import requests
import sys
import threading

got_new_input = threading.Event()
_got_new_input_lock = threading.Lock()
_out_lock = threading.Lock()

class CloseFlag:
    def __init__(self):
        self.close = False
    
    def __bool__(self):
        return self.close

def input_handler(q:queue.Queue):
    while True:
        line = sys.stdin.readline()
        if not line:
            return
        q.put(json.loads(line))
        with _got_new_input_lock:
            got_new_input.set()

def handle_mic(mic_id:str, r:requests.Response, flag:CloseFlag):
    last_volume = 0
    for chunk in r.iter_content(2):
        if flag:
            return
        if not chunk:
            return
        volume = int.from_bytes(chunk, "big", signed=False)
        if volume != last_volume:
            with _out_lock:
                sys.stdout.write(f"{json.dumps({"name":"change_volume", "data":{"id": mic_id, "volume": volume}})}\n")
                sys.stdout.flush()
            last_volume = volume
        if flag:
            return

def main(url_prefix:str, q:queue.Queue):
    global run
    threads:dict[str, tuple[threading.Thread, CloseFlag]] = {}
    session = requests.Session()
    while run:
        got_new_input.wait()
        while run:
            try:
                instruction:dict[str] = q.get(block=False)
            except queue.Empty:
                with _got_new_input_lock:
                    got_new_input.clear()
                break
            name:str = instruction["name"]
            data = instruction["data"]
            if name == "new_mic":
                mic_id:str = data["id"]
                r = session.get(f"{url_prefix}/api/microphone/volume/stream?id={mic_id}", stream=True)
                if not r.ok:
                    continue
                flag = CloseFlag()
                thread = threading.Thread(target=handle_mic, args=(mic_id, r, flag), daemon=True)
                thread.start()
                threads[mic_id] = thread, flag
            elif name == "drop_mic":
                thread_info = threads.pop(data["id"], None)
                if thread_info is not None:
                    thread_info[1].close = True
            elif name == "end":
                run = False
        if not run:
            break
    

if __name__ == "__main__":
    run = True
    url_prefix:str = sys.argv[1]
    q = queue.Queue()
    input_thread = threading.Thread(target=input_handler, args=(q,), daemon=True)
    input_thread.start()
    main(url_prefix, q)