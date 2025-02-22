import json
import threading
from typing import Generator
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
    def __init__(self, id:UUID, queue:list[Event]|None=None):
        self.id = id
        self.queue = [] if queue is None else queue
        self.lock = threading.Lock()

    def __len__(self):
        return len(self.queue)

    def push(self, *events:Event):
        with self.lock:
            self.queue.extend(events)

    def dump(self)->Generator[Event, None, None]:
        if self.queue:
            with self.lock:
                for event in self.queue:
                    yield event
                self.queue.clear()

    def clear(self):
        with self.lock:
            self.queue.clear()


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
    

default_container = EventBucketContainer()

def new_bucket(id:UUID|None=None, container:EventBucketContainer=default_container):
    return container.new_bucket(id)

def remove_bucket(x:UUID|EventBucket, container:EventBucketContainer=default_container):
    return container.remove_bucket(x)

def dispatch(*events:Event, container:EventBucketContainer=default_container):
    return container.dispatch(*events)