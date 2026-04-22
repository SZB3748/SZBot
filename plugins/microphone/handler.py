from . import exceptions
import base64
import json
import os
import pyaudio
import queue
import subprocess
import sys
import threading
import traceback
from typing import Generator
from uuid import UUID, uuid4, uuid5

DIR = os.path.dirname(__file__)
INPUT_PROC_FILE = os.path.join(DIR, "handler_input_proc.py")

NS_UUID = UUID("95c379e4-1b9f-40f8-b130-fc61d1362c52")

DEFAULT_MIC_FORMAT = pyaudio.paInt16
DEFAULT_MIC_CHANNELS = 2
DEFAULT_MIC_RATE = 44100
DEFAULT_MIC_CHUNK = 1024

_format_map = {
    "float32": pyaudio.paFloat32,
    "int32": pyaudio.paInt32,
    "int24": pyaudio.paInt24,
    "int16": pyaudio.paInt16,
    "int8": pyaudio.paInt8,
    "uint8": pyaudio.paUInt8
}
_rev_format_map = {v:k for k,v in _format_map.items()}

Frame = tuple[bytes, int, int]

class AudioBucket:
    def __init__(self, id:UUID):
        self.id = id
        self.frames:list[Frame] = []
        self.frames_lock = threading.Lock()
        self.audio_ready = threading.Event()

    def get_frames(self)->Generator[Frame, None, None]:
        with self.frames_lock:
            yield from self.frames
            self.frames.clear()
            self.audio_ready.clear()

    def wait(self, timeout:float|None=None):
        return self.audio_ready.wait(timeout)
    
    def add_frames(self, *frames:Frame):
        with self.frames_lock:
            self.frames.extend(frames)
            self.audio_ready.set()

class Microphone:
    def __init__(self, name:str, enabled:bool, format:int|str, channels:int, rate:int, frames_per_buffer:int):
        self.name = name
        self.enabled = enabled
        self.format = _format_map[format] if isinstance(format, str) else format
        self.channels = channels
        self.rate = rate
        self.frames_per_buffer = frames_per_buffer
        self.is_on = False


    def __getstate__(self):
        return {
            "name": self.name,
            "enabled": self.enabled,
            "format": _rev_format_map[self.format],
            "channels": self.channels,
            "rate": self.rate,
            "frames_per_buffer": self.frames_per_buffer,
            "is_on": self.is_on
        }
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.enabled = bool(d["enabled"])
        format = d["format"]
        self.format = _format_map[format] if isinstance(format, str) else int(format)
        self.channels = int(d["channels"])
        self.rate = int(d["rate"])
        self.frames_per_buffer = int(d["frames_per_buffer"])
        self.is_on = bool(d["is_on"])

INST_STREAM_START   = "stream_start"
INST_STREAM_STOP    = "stream_stop"
INST_FRAME          = "frame"

class MicrophoneHandler:
    def __init__(self):
        self.mics:dict[UUID, Microphone] = {}
        self.buckets:dict[UUID, AudioBucket] = {}
        self.mic_map:dict[UUID, set[UUID]] = {}
        self.bucket_map:dict[UUID, set[UUID]] = {}
        self.do_handle = False
        self.has_buckets = threading.Event()
        self.proc:subprocess.Popen = None

    def from_init(self, d:list[dict[str]]):
        pya = pyaudio.PyAudio()
        self.mics.clear()
        self.buckets.clear()
        self.mic_map.clear()
        self.bucket_map.clear()
        self.has_buckets.clear()
        default_info = pya.get_default_input_device_info()
        device_infos:dict[str,pyaudio._PaDeviceInfo] = {info["name"]:info for i in range(pya.get_device_count()) if (info:=pya.get_device_info_by_index(i)).get("maxInputChannels",0) > 0}
        names:dict[str, int] = {}
        for entry in d:
            if "name" in entry:
                name = entry["name"]
                for devicename in device_infos:
                    if name in devicename:
                        info = device_infos[devicename]
                        break
                else:
                    continue
            else:
                name = default_info["name"]
                info = default_info
            enabled = entry.get("enabled", True)
            if "format" in entry:
                format = _format_map[entry["format"]]
            else:
                format = DEFAULT_MIC_FORMAT
            channels = entry.get("channels", min(DEFAULT_MIC_CHANNELS, info["maxInputChannels"]))
            rate = entry.get("rate", DEFAULT_MIC_RATE)
            frames_per_buffer = entry.get("frames_per_buffer", DEFAULT_MIC_CHUNK)
            names[name] = nameindex = names.get(name, -1) + 1
            self.mics[uuid5(NS_UUID, f"{name}\n{nameindex}")] = Microphone(name=name, enabled=enabled, format=format, channels=channels, rate=rate, frames_per_buffer=frames_per_buffer)

    def start_stream(self, micid:UUID, mic:Microphone):
        self.proc.stdin.write(f"{json.dumps({"name":INST_STREAM_START, "data":{"id":str(micid), **mic.__getstate__()}})}\n")
        self.proc.stdin.flush()
        mic.is_on = True
            
    def stop_stream(self, micid:UUID, mic:Microphone):
        self.proc.stdin.write(f"{json.dumps({"name":INST_STREAM_STOP, "data": {"id": str(micid)}})}\n")
        self.proc.stdin.flush()
        mic.is_on = False

    def new_bucket(self, *mic_ids:UUID):
        disabled:list[str] = []
        for id in mic_ids:
            if id not in self.mics:
                return
            elif not self.mics[id].enabled:
                disabled.append(str(id))
        if disabled:
            return exceptions.MicDisabledException(",".join(disabled))

        bucket_id = uuid4()
        for id in mic_ids:
            if id in self.mic_map:
                self.mic_map[id].add(bucket_id)
            else:
                self.mic_map[id] = {bucket_id}
                self.start_stream(id, self.mics[id])
        self.bucket_map[bucket_id] = set(mic_ids)
        self.buckets[bucket_id] = bucket = AudioBucket(bucket_id)
        self.has_buckets.set()
        return bucket

    def drop_bucket(self, bucket:AudioBucket|UUID):
        if isinstance(bucket, AudioBucket):
            bucket = bucket.id
        micnames = self.bucket_map.pop(bucket, None)
        if micnames:
            for mic_id in micnames:
                if mic_id not in self.mic_map:
                    continue
                bucketset = self.mic_map[mic_id]
                if bucket in bucketset:
                    bucketset.remove(bucket)
                if not bucketset:
                    del self.mic_map[mic_id]
                    self.stop_stream(mic_id, self.mics[mic_id])
        if bucket in self.buckets:
            del self.buckets[bucket]
        if not self.buckets:
            self.has_buckets.clear()

    def add_mic(self, mic:Microphone, nameindex:int=0):
        id = uuid5(NS_UUID, f"{mic.name}\n{nameindex}")
        self.mics[id] = mic
        if mic.enabled and self.do_handle:
            return self.start_stream(id, mic)

    def handle_buckets(self):
        self.do_handle = True
        q = queue.Queue()
        def queue_thread_handler():
            while self.do_handle:
                line = self.proc.stdout.readline()
                if not line:
                    return
                q.put(json.loads(line))
        queue_thread = threading.Thread(target=queue_thread_handler, daemon=True)
        queue_thread.start()

        for id, mic in self.mics.items():
            if mic.enabled and self.mic_map.get(id, None):
                self.start_stream(id, mic)

        while self.do_handle:
            try:
                instruction:dict[str] = q.get()
                name = instruction["name"]
                data = instruction["data"]
            except KeyboardInterrupt:
                self.do_handle = False
                break
            except Exception as e:
                print(f"microphone {mic.name} ({mic_id}) got {type(e).__name__} error:")
                traceback.print_exception(e)
                self.stop_stream(mic_id)
                continue
            if name == INST_FRAME:
                mic_id = UUID(data["id"])
                mic = self.mics.get(mic_id)
                if mic is None:
                    continue
                elif not mic.is_on:
                    self.stop_stream(id, mic)
                    continue
                frame_s:str = data["frame"]
                frame = base64.b64decode(frame_s.encode("utf-8"))
                bucket_ids = self.mic_map.get(mic_id, None)
                if bucket_ids:
                    for bucket in (self.buckets[id] for id in bucket_ids):
                        bucket.add_frames((frame, mic.format, mic.channels))
            self.has_buckets.wait()
    
    def handle(self):
        self.proc = subprocess.Popen([sys.executable, INPUT_PROC_FILE], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.handle_buckets()
        finally:
            self.proc.terminate()
            self.proc.wait(0.5)
            self.proc.kill()