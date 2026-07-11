import actions
import aiohttp
import asyncio
import atexit
import exiting
import logenv
from overlays import media
import pyaudio
import pydub
import tempfile
import threading
import traceback
from typing import Literal
from uuid import UUID, uuid4

DEFAULT_MEDIA_DOWNLOAD_CHUNK_SIZE = 4096

LOC_TYPE_LOCAL = "local"
LOC_TYPE_URL = "url"

LocationType = Literal["local","url"]

PYAUDIO = pyaudio.PyAudio()
atexit.register(PYAUDIO.terminate)

class PlayerQueueItem:
    def __init__(self, media_name:str, location_type:LocationType=LOC_TYPE_LOCAL, url_prefix:str|None=None, start_ms:int=0, output_device_name:str|None=None):
        self.media_name = media_name
        self.location_type:LocationType = location_type
        self.url_prefix = url_prefix
        self.start_ms = start_ms
        self.output_device_name = output_device_name
        self._audio:pydub.AudioSegment|None = None
        self._started_prepping = False
        self._done_prepping = threading.Event()
        self._id = uuid4()
        self._next:PlayerQueueItem|None = None

    async def prep(self, download_chunk_size=DEFAULT_MEDIA_DOWNLOAD_CHUNK_SIZE):
        self._started_prepping = True
        try:
            if self._audio is not None:
                return
            elif self.location_type == "local":
                entry = media.load_media_entries().get(self.media_name, None)
                if entry is not None:
                    mime = entry.resolve_type()
                    if mime is not None and mime.startswith("audio/"):
                        self._audio = pydub.AudioSegment.from_file(entry.get_path())
                #TODO warn audio media entry of given name could not be found
            elif self.location_type == "url":
                async with aiohttp.ClientSession() as s:
                    async with s.get(f"{self.url_prefix}/api/media?name={self.media_name}") as r:
                        r.raise_for_status()
                        if r.content_type.startswith("audio/"):
                            with tempfile.TemporaryFile("wb") as tf:
                                async for chunk in r.content.iter_chunked(download_chunk_size):
                                    tf.write(chunk)
                                self._audio = pydub.AudioSegment.from_file(tf.name)
        finally:
            self._done_prepping.set()
    
    def is_prepped(self):
        return self._audio is not None
    
    def started_prep(self):
        return self._started_prepping
    
    def failed_prep(self):
        return self.is_done_prep() and not self.is_prepped()
    
    def is_done_prep(self):
        return self._done_prepping.is_set()

    def wait_for_prep(self):
        self._done_prepping.wait()
        x = self.is_prepped()
        return x

class PlayerQueue:
    def __init__(self):
        self._head:PlayerQueueItem|None = None
        self._tail:PlayerQueueItem|None = None
        self._length = 0

    def __len__(self):
        return self._length

    def enqueue(self, item:PlayerQueueItem):
        if self._tail is None:
            self._head = self._tail = item
        else:
            self._tail._next = item
            self._tail = item
        self._length += 1

    def _pop(self, index:int):
        if self._head is None:
            self._length = 0
            return None
        elif index == 0:
            return self._head
        elif index > 0:
            cur = self._head
            target = index-1
            i = 0
            while i < target:
                i += 1
                cur = cur._next
                if cur is None:
                    self._length = i
                    return None
            node = cur._next
            if node is None:
                self._length = index
                return None
            return cur
        
    def pop(self, index:int=0, count:int=1):
        l:list[PlayerQueueItem] = []
        if count <= 0:
            return l
        pre = self._pop(index)
        if pre is None:
            return l
        if index == 0 and pre is self._head:
            i = 0
            node = pre
            while i < count:
                l.append(node)
                if node._next is None:
                    break
                nnode = node._next
                node._next = None
                node = nnode
                i += 1
            self._head = node._next
            if self._head is None:
                self._tail = None
        elif pre._next is None:
            return l
        else:
            node = pre._next
            while i < count:
                l.append(node)
                if node._next is None:
                    break
                nnode = node._next
                node._next = None
                node = nnode
                i += 1
            if node is self._tail:
                self._tail = pre
            pre._next = node._next

        self._length = max(self._length - len(l), 0)
        return l
    
    def peek(self, index:int=0):
        if index < 0:
            return None
        cur = self._head
        for i in range(index):
            cur = cur._next
            if cur is None:
                self._length = i+1
                return None
        return cur

    def peek_slice(self, start:int|None=None, stop:int|None=None)->list[PlayerQueueItem]:
        if self._head is None:
            return []
        index = 0 if start is None else start

        if index < 0:
            return []
        cur = self._head
        for i in range(index):
            cur = cur._next
            if cur is None:
                self._length = i+1
                return []
        l = [cur]
        x = self._length if stop is None else stop
        for i in range(index+1, x):
            cur = cur._next
            if cur is None:
                self._length = i+1
                return l
            l.append(cur)
        return l

class Playback:
    def __init__(self, audio:pydub.AudioSegment|None=None, start_ms:int=0, output_device_name:str|None=None, frames_per_write:int=1024):
        self.audio = audio
        self.start_ms = start_ms
        self.output_device_name = output_device_name
        self._frames_per_write = frames_per_write
        self._elapsed:int = 0
        self._stream:pyaudio.Stream|None = None
        self._last_output_name:str|None = None
        self._last_output_index:int|None = None
        self._event = threading.Event()
        self._bytes_per_second:int|None=None

    def _get_output_device_index(self)->int|None:
        if self.output_device_name == self._last_output_name:
            return self._last_output_index
        name_matches:list[tuple[str, int]] = []
        for i in range(PYAUDIO.get_device_count()):
            device_info = PYAUDIO.get_device_info_by_index(i)
            n = device_info["name"]
            if device_info["maxOutputChannels"] > 0 and self.output_device_name.lower() in n.lower():
                name_matches.append((n, i))
        if name_matches:
            if len(name_matches) > 1:
                name_matches.sort(key=lambda pair: pair[0])
                for n, i in name_matches:
                    if n in self.output_device_name:
                        break
            else:
                n, i = name_matches[0]
            self._last_output_name = n
            self._last_output_index = i
            return i
        else:
            self._last_output_name = self._last_output_index = None
            return None

    def _audio_callback(self, in_data:bytes|None, frame_count:int, time_info:dict[str,float], status:int):
        end_position = self._elapsed + frame_count * self.audio.sample_width * self.audio.channels
        chunk = self.audio.raw_data[self._elapsed:end_position]
        self._elapsed = end_position

        if end_position >= len(self.audio.raw_data):
            code = pyaudio.paComplete
        else:
            code = pyaudio.paContinue
        return chunk, code

    def play(self):
        if self.audio is None:
            return
        if self._stream is None:
            self._stream = PYAUDIO.open(
                format=PYAUDIO.get_format_from_width(self.audio.sample_width),
                channels=self.audio.channels,
                rate=self.audio.frame_rate,
                output=True,
                stream_callback=self._audio_callback,
                output_device_index=self._get_output_device_index(),
                frames_per_buffer=self._frames_per_write
            )
            self._elapsed = self.start_ms * self._bytes_per_second
        self._elapsed = max(0, min(self._elapsed, len(self.audio.raw_data)))
        self._stream.start_stream()
        self._event.set()
    
    def pause(self):
        if self._stream is not None:
            self._stream.stop_stream()
    
    def stop(self):
        if self.audio is not None:
            self._elapsed = len(self.audio.raw_data)
            self.audio = None
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        self._event.set()

    def reset(self, audio:pydub.AudioSegment, start_secs:float=0.0):
        if audio is not self.audio:
            self.audio = audio
            self._bytes_per_second = self.audio.frame_rate * self.audio.channels * self.audio.sample_width
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
                self._stream = None
        self.start_secs = start_secs
        self._elapsed = int(self.start_secs * self._bytes_per_second)

    def get_elapsed(self):
        if self._bytes_per_second is None:
            return 0.0
        else:
            return self._elapsed / self._bytes_per_second
        
    def get_elapsed_ms(self):
        if self._bytes_per_second is None:
            return 0.0
        else:
            return self._elapsed / self._bytes_per_second * 1000
    
    def set_elapsed(self, seconds:float):
        if self.audio is not None:
            seconds = max(0, min(seconds, len(self.audio) / 1000))
        self._elapsed = int(seconds * self._bytes_per_second)
        return seconds
    
    def get_duration(self):
        return 0 if self.audio is None else len(self.audio) / 1000
    
    def get_duration_ms(self):
        return 0 if self.audio is None else len(self.audio)
    
    def is_playing(self):
        if self._stream is None:
            return False
        else:
            return bool(self._stream.is_active())
        
    def is_done(self):
        #if theres a little more audio to play then the stream may still be active
        return self.audio is None or self._stream is None or (self._elapsed >= len(self.audio.raw_data) and not self._stream.is_active())
        
    def wait(self):
        while not self.is_done():
            if self._stream is None:
                self._event.wait()
            else:
                self._stream
            self._event.clear()


class Player:
    def __init__(self, prep_first:int=2):
        self.prep_first = prep_first
        self._current:PlayerQueueItem|None = None
        self.playback = Playback()
        self._run = True
        self._queue = PlayerQueue()
        self._queuelock = threading.Lock()
        self._queue_has_entries = threading.Event()

    def add_to_queue(self, media_name:str, location_type:LocationType, url_prefix:str|None=None, output_device_name:str|None=None):
        item = PlayerQueueItem(media_name, location_type, url_prefix=url_prefix, output_device_name=output_device_name)
        with self._queuelock:
            self._queue.enqueue(item)
            self._queue_has_entries.set()
            return item._id, len(self._queue)

    def skip(self, position:int=0, count:int=1):
        with self._queuelock:
            popped = self._queue.pop(position, count)
            if len(self._queue) < 1:
                self._queue_has_entries.clear()
            if popped:
                for item in popped:
                    if item is self._current:
                        self._current = None
                        self.playback.stop()
                        break
        return popped
    
    def skip_id(self, id:UUID|PlayerQueueItem, count:int=1)->list[PlayerQueueItem]:
        i = 0
        index = None
        cur = self._queue._head
        if isinstance(id, UUID):
            with self._queuelock:
                while cur is not None:
                    if cur._id == id:
                        index = i
                        break
                    cur = cur._next
                    i += 1
        else:
            with self._queuelock:
                while cur is not None:
                    if cur is id:
                        index = i
                        break
                    cur = cur._next
                    i += 1
        if index is not None:
            return self.skip(index, count)
        else:
            return []

    def stop(self):
        self._run = False
        self._queue_has_entries.set()
        self.playback.stop()

    def handle(self):
        futures:set[asyncio.Future] = set()
        
        @exiting.register_cleanup_listener
        def _cleanup(ctx):
            exiting.unregister_cleanup_listener(_cleanup)
            logenv.main.info("stopping sounds player handler")
            self._run = False
            self._queue_has_entries.set()
            self.playback.stop()
            logenv.main.info("stopped sounds player handler")

        while self._run:
            if not self._queue_has_entries.is_set():
                for future in [future for future in futures if future.done()]:
                    futures.remove(future)
                self._queue_has_entries.wait()
                if not self._run:
                    break

            with self._queuelock:
                first = self._queue.peek()
                if first is None:
                    self._queue_has_entries.clear()
                    continue

                prep_count = min(self.prep_first, 1)
                needs_prep = [item for item in self._queue.peek_slice(stop=prep_count) if not item.started_prep()]
                if needs_prep:
                    future = asyncio.run_coroutine_threadsafe(prep_sounds(needs_prep), loop=actions.shared_loop)
                    if first in needs_prep:
                        future.result()
                    else:
                        futures.add(future)

                #remove any that failed to prep
                
                while not first.wait_for_prep():
                    self._queue.pop()
                    first = self._queue.peek()
                    while first is not None and first.failed_prep():
                        self._queue.pop()
                        first = self._queue.peek()
                    if first is None:
                        break
                    if not first.started_prep():
                        future = asyncio.run_coroutine_threadsafe(prep_sounds([first]), loop=actions.shared_loop)
                        future.result()

                if first is None:
                    self._queue_has_entries.clear()
                    continue

                self._current = first

            self.playback.reset(self._current._audio, self._current.start_ms)
            self.playback.play()
            self.playback.wait()

            if not self._run:
                break
            
            with self._queuelock:
                first = self._queue.peek()
                if first is self._current:
                    self._queue.pop()

        exiting.unregister_cleanup_listener(_cleanup)

async def prep_sounds(sounds:list[PlayerQueueItem], download_chunk_size:int=DEFAULT_MEDIA_DOWNLOAD_CHUNK_SIZE):
    try:
        if len(sounds) > 1:
            await asyncio.gather(*(sound.prep(download_chunk_size=download_chunk_size) for sound in sounds))
        elif len(sounds):
            await sounds[0].prep(download_chunk_size=download_chunk_size)
    except Exception as e:
        logenv.main.error_exception(e, logenv.EXCEPTION_TRACEBACK)


main_player:Player|None = None