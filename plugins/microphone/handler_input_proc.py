import base64
import exceptions
import json
import pyaudio
import queue
import sys
import threading
import traceback
from uuid import UUID

INST_STREAM_START   = "stream_start"
INST_STREAM_STOP    = "stream_stop"
INST_END            = "end"
INST_FRAME          = "frame"

_format_map = {
    "float32": pyaudio.paFloat32,
    "int32": pyaudio.paInt32,
    "int24": pyaudio.paInt24,
    "int16": pyaudio.paInt16,
    "int8": pyaudio.paInt8,
    "uint8": pyaudio.paUInt8
}

streams:dict[UUID, pyaudio.Stream] = {}

def get_device_index(pya:pyaudio.PyAudio, name:str, channels:int)->int|None:
    for i in range(pya.get_device_count()):
        info = pya.get_device_info_by_index(i)
        channels = info.get("maxInputChannels", 0)
        if channels > 0 and name in info["name"]:
            if channels > channels:
                raise exceptions.BadMicSettingsException("Too many channels requested.")
            return i

def stdin_thread_handler(q:queue.Queue):
    while True:
        q.put(json.loads(sys.stdin.readline()))


if __name__ == "__main__":
    run = True
    pya = pyaudio.PyAudio()
    q = queue.Queue()
    streams:dict[UUID, tuple[pyaudio.Stream, int]] = {}
    remove_after = []

    stdin_thread = threading.Thread(target=stdin_thread_handler, args=(q,), daemon=True)
    stdin_thread.start()


    while run:
        while run:
            try:
                instruction:dict[str] = q.get(block=False)
            except queue.Empty:
                break
            except KeyboardInterrupt:
                run = False
                break
            else:
                name = instruction["name"]
                data = instruction["data"]
                if name == INST_STREAM_START:
                    id = UUID(data["id"])
                    name = data["name"]
                    channels = data["channels"]
                    frames_per_buffer = data["frames_per_buffer"]
                    index = get_device_index(pya, name, channels)
                    if index is None:
                        continue
                    stream = pya.open(rate=data["rate"], channels=channels, format=_format_map[data["format"]], input=True, input_device_index=index, frames_per_buffer=frames_per_buffer)
                    if stream is None:
                        continue
                    streams[id] = stream, frames_per_buffer
                elif name == INST_STREAM_STOP:
                    id = UUID(data["id"])
                    streamdata = streams.pop(id, None)
                    if streamdata is None:
                        continue
                    streamdata[0].close()
                elif name == INST_END:
                    run = False
        if not run:
            break

        for id, (stream, frames_per_buffer) in streams.items():
            try:
                frame = stream.read(frames_per_buffer)
            except KeyboardInterrupt:
                run = False
                break
            except IOError as e:
                print(f"microphone {id} got {type(e).__name__} error:")
                traceback.print_exception(e)
                stream.close()
                remove_after.append(id)
            else:
                sys.stdout.write(f"{json.dumps({"name": INST_FRAME, "data": {"id": str(id), "frame": base64.b64encode(frame).decode("utf-8")}})}\n")
                sys.stdout.flush()
        if remove_after:
            for id in remove_after:
                del streams[id]
            remove_after.clear()

    for stream, _ in streams.values():
        stream.close()
    streams.clear()