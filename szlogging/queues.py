from . import destinations, messages, transforms
import threading
from typing import Iterable

QueueOutputs = list[tuple[destinations.Destination, transforms.Transformation]]

class _queue_entry:
    __slots__ = "m", "o"
    def __init__(self, m:messages.Message, o:QueueOutputs):
        self.m = m
        self.o = o


class Queue:
    def __init__(self):
        self._queue:list[_queue_entry] = []
        self._queue_ready = threading.Event()
        self._lock = threading.Lock()

    def push(self, message:messages.Message, outputs:QueueOutputs):
        with self._lock:
            self._queue.append(_queue_entry(message, outputs))
            self._queue_ready.set()

    def send_all(self, block:bool=False):
        if block:
            self._queue_ready.wait()

        with self._lock:
            q = self._queue.copy()
            self._queue.clear()
            self._queue_ready.clear()

        for e in q:
            for d, t in e.o:
                if d.threshold_level is None or e.m.level.value >= d.threshold_level.value:
                    send(e.m, t, d)


def send(message:messages.Message, transform:transforms.Transformation, dest:destinations.Destination):
    return dest(transform(message))