import json
import threading
from typing import Callable, Generator
from uuid import UUID, uuid4

class Event:
    def __init__(self, name:str, data:dict[str]|None|None=None):
        self.name = name
        self.data = {} if data is None else data

    def to_json(self):
        return json.dumps({
            "name": self.name,
            "data": self.data
        })

class EventBucket:
    """Collects events so that they can later be handled all at once."""
    def __init__(self, id:UUID, queue:list[Event]|None=None):
        self.id = id
        self.queue = [] if queue is None else queue
        self.lock = threading.Lock()
        self._event = threading.Event()

    def __len__(self):
        return len(self.queue)

    def wait(self, timeout:float|None=None):
        """Wait for an event to be added to the bucket."""
        return self._event.wait(timeout)

    def push(self, *events:Event):
        """Add an event to the bucket."""
        with self.lock:
            self.queue.extend(events)
            self._event.set()

    def dump(self)->Generator[Event, None, None]:
        """Returns a generator to handle the events with. After iterating over all the events, the bucket is emptied."""
        if self.queue:
            with self.lock:
                for event in self.queue:
                    yield event
                self.queue.clear()
                self._event.clear()

    def clear(self):
        """Clears all the events in the bucket without handling them."""
        with self.lock:
            self.queue.clear()
            self._event.clear()


class EventBucketContainer:
    def __init__(self, buckets:dict[UUID, EventBucket]|None=None):
        self.buckets = {} if buckets is None else buckets

    def new_bucket(self, id:UUID|None=None)->EventBucket:
        if id is None:
            id = uuid4()
        self.buckets[id] = bucket = EventBucket(id)
        return bucket

    def remove_bucket(self, x:UUID|EventBucket)->EventBucket|None:
        id = x.id if isinstance(x, EventBucket) else x
        return self.buckets.pop(id, None)
    
    def dispatch(self, *events:Event):
        for bucket in self.buckets.values():
            bucket.push(*events)

EventListenerCallback = Callable[[Event], None]

class EventListener:
    def __init__(self, callback:EventListenerCallback, once:bool=False):
        self.callback = callback
        self.once = once

class EventListenerCollection:
    def __init__(self, listeners:dict[str, list[EventListener]]|None=None):
        self.listeners = {} if listeners is None else listeners

    def add_listener(self, name:str, x:EventListener|EventListenerCallback):
        if not isinstance(x, EventListener):
            x = EventListener(x)
        if name in self.listeners:
            self.listeners[name].append(x)
        else:
            self.listeners[name] = [x]

    def listener(self, name:str):
        def decor(f:EventListenerCallback):
            self.add_listener(name, f)
            return f
        return decor

    def handle_event(self, event:Event):
        if event.name in self.listeners:
            i = 0
            listeners = self.listeners[event.name]
            while i < len(listeners):
                listener = listeners[i]
                listener.callback(event)
                if listener.once:
                    listeners.pop(i)
                else:
                    i += 1
            if not listeners:
                self.listeners.pop(event.name)
    

default_container = EventBucketContainer()
default_listeners = EventListenerCollection()

def new_bucket(id:UUID|None=None, container:EventBucketContainer=default_container):
    return container.new_bucket(id)

def remove_bucket(x:UUID|EventBucket, container:EventBucketContainer=default_container):
    return container.remove_bucket(x)

def dispatch(*events:Event, container:EventBucketContainer=default_container):
    return container.dispatch(*events)

def add_listener(name:str, x:EventListener|EventListenerCallback, collection:EventListenerCollection=default_listeners):
    return collection.add_listener(name, x)

def listener(name:str, collection:EventListenerCollection=default_listeners):
    return collection.listener(name)

def handle_event(event:Event, collection:EventListenerCollection=default_listeners):
    return collection.handle_event(event)