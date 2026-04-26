from datetime import datetime, timedelta, timezone
from enum import Enum
import io
import json
import os
import subprocess
import sys
import threading
import traceback
from typing import Callable, Self

DIR = os.path.dirname(__file__)
MIC_VOLUME_PROC_FILE = os.path.join(DIR, "microphone_volumecheck_proc.py")

class TransitionMode(Enum):
    HOLD = 1
    TRIGGER_DOWN = 2
    TRIGGER_UP = 3

TimeoutChange = tuple[str, timedelta] #change to the specified state after the given timeout

class MediaReference:
    def __init__(self, content_name:str, border_name:str):
        self.content_name = content_name
        self.border_name = border_name

    def __getstate__(self):
        return self.__dict__.copy()
    
    def __setstate__(self, d:dict[str]):
        self.__init__(**d)

class State:
    def __init__(self, name:str, media:MediaReference, change:TimeoutChange=None, allow_event_interrupt:bool=False):
        self.name = name
        self.media = media
        self.change = change
        self.allow_event_interrupt = allow_event_interrupt

    def __eq__(self, other):
        if isinstance(other, State):
            return self is other or self.name == other.name
        return super().__eq__(other)
    
    def __hash__(self):
        return hash(str(id(type(self))) + self.name)

    def __getstate__(self):
        rtv:dict[str] = {"media": self.media.__getstate__(), "allow_event_interrupt": self.allow_event_interrupt}
        if self.change is not None:
            rtv["change"] = {
                "destination": self.change[0],
                "timeout": self.change[1].total_seconds()
            }
        return rtv

    def __setstate__(self, d:dict[str]):
        if "name" in d:
            self.name:str = d["name"]
        self.media = MediaReference.__new__(MediaReference)
        self.media.__setstate__(d["media"])
        dchange = d.get("change", None)
        if isinstance(dchange, dict):
            self.change:TimeoutChange = dchange["destination"], timedelta(seconds=dchange["timeout"])
        else:
            self.change = None
        self.allow_event_interrupt = bool(d.get("allow_event_interrupt", False))

class Transition:
    def __init__(self, keybind:str, mode:TransitionMode, destination:str, pop_destination:str|None=None):
        self.keybind = keybind
        self.mode = mode
        self.destination = destination
        self.pop_destination = pop_destination #with StateMapNavigator default behavior, only applicable for hold mode

    def __getstate__(self):
        d = {
            "keybind": self.keybind,
            "mode": self.mode.name,
            "destination": self.destination
        }
        if self.pop_destination is not None:
            d["pop_destination"] = self.pop_destination
        return d

    def __setstate__(self, d:dict[str]):
        dmode = d["mode"]
        if isinstance(dmode, str):
            mode = TransitionMode[dmode]
        else:
            mode = TransitionMode(dmode)
        self.__init__(d["keybind"], mode, d["destination"], d.get("pop_destination", None))

class EventCondition:
    CATEGORY_NAME:str = NotImplemented

    @classmethod
    def cast(cls, condition:Self):
        if not issubclass(condition.__class__, cls):
            condition.__class__ = cls
        return condition

    def __init__(self, name:str, data:dict[str]):
        self.name = name
        self.data = data

    def __getstate__(self)->dict[str]:
        return self.__dict__.copy()
    
    def __setstate__(self, d:dict[str]):
        self.name = d["name"]
        self.data = d["data"]
    
    def handle(self, negotiator:"EventNegotiator", event:"Event"):
        raise NotImplementedError

CONDITION_CATEGORY_STATE_MATCH = "state_match"
CONDITION_CATEGORY_MEDIA_MATCH = "media_match"
CONDITION_CATEGORY_KEYBINDS_IDLE = "keybinds_idle"
CONDITION_CATEGORY_ACTIVE_LIMIT = "active_limit"
CONDITION_CATEGORY_INACTIVE = "inactive"
CONDITION_CATEGORY_MIC_ACTIVITY = "mic_activity"

class StateMatchCondition(EventCondition):
    """Condition that is met when the current state matches one of the given names."""
    CATEGORY_NAME = CONDITION_CATEGORY_STATE_MATCH
    def __init__(self, *names:str, **data):
        data["names"] = list(names)
        super().__init__(self.CATEGORY_NAME, data)

    @property
    def names(self)->list[str]:
        return self.data["names"]
    
    @names.setter
    def names(self, value:list[str]):
        self.data["names"] = value

    def handle(self, negotiator:"EventNegotiator", event:"Event")->bool:
        stack = negotiator.navstack_callback()
        if stack is None or stack.state is None:
            return False
        return stack.state.name in self.names

class MediaMatchCondition(EventCondition):
    """Condition that is met when the current state uses media with one of the given names, and optionally from the given location (e.g. border, content)."""
    CATEGORY_NAME = CONDITION_CATEGORY_MEDIA_MATCH

    def __init__(self, *names:str, location:str|None=None, **data):
        data["names"] = list(names)
        if location is not None:
            data["location"] = location
        super().__init__(self.CATEGORY_NAME, data)

    @property
    def names(self)->list[str]:
        return self.data["names"]
    
    @names.setter
    def names(self, value:list[str]):
        self.data["names"] = value

    @property
    def location(self)->str|None:
        return self.data.get("location", None)
    
    @location.setter
    def location(self, value:str|None):
        self.data["location"] = value

    @location.deleter
    def location(self):
        if "location" in self.data:
            del self.data["location"]
    
    def handle(self, negotiator:"EventNegotiator", event:"Event")->bool:
        stack = negotiator.navstack_callback()
        if stack is None or stack.state is None:
            return False
        media = stack.state.media
        border = self.location is None or self.location == "border"
        content = self.location is None or self.location == "content"
        return (border and media.border_name in self.names) or (content and media.content_name in self.names)


class DurationConditionType(EventCondition):
    """Type of conditions which stores a timespan in seconds."""
    def __init__(self, seconds:float|timedelta, **data):
        data["seconds"] = seconds.total_seconds() if isinstance(seconds, timedelta) else seconds
        assert isinstance(self.CATEGORY_NAME, str), f"EventCondition {type(self).__name__} must define a CATEGORY_TYPE, got {self.CATEGORY_NAME}"
        super().__init__(self.CATEGORY_NAME, data)

    @property
    def seconds(self)->float:
        return self.data["seconds"]

    @seconds.setter
    def seconds(self, value:float|timedelta):
        self.data["seconds"] = value.total_seconds() if isinstance(value, timedelta) else value

class IdleCondition(DurationConditionType):
    """Condition that is met when no keybinds have been entered for the given amount of seconds."""
    CATEGORY_NAME = CONDITION_CATEGORY_KEYBINDS_IDLE

    def handle(self, negotiator:"EventNegotiator", event:"Event")->bool:
        return not negotiator.keybind_holding and (datetime.now(timezone.utc) - negotiator.last_keybind_trigger).total_seconds() >= self.seconds

class ActiveLimitCondition(DurationConditionType):
    """Condition that is not met when all of an event's conditions have been met for more than the given amount of seconds."""
    CATEGORY_NAME = CONDITION_CATEGORY_ACTIVE_LIMIT

    def handle(self, negotiator:"EventNegotiator", event:"Event")->bool:
        state = negotiator.event_activity_states.get(event.name, None)
        if state is None:
            return True
        active, started = state
        return not active or (datetime.now(timezone.utc) - started).total_seconds() < self.seconds

class InactiveCondition(DurationConditionType):
    """Condition that is met when all of an event's conditions haven't been met for more than the given amount of seconds."""
    CATEGORY_NAME = CONDITION_CATEGORY_INACTIVE

    def handle(self, negotiator:"EventNegotiator", event:"Event")->bool:
        state = negotiator.event_activity_states.get(event.name, None)
        if state is None:
            state = False, negotiator.__activity_state_default
        active, started = state
        return active or (datetime.now(timezone.utc) - started).total_seconds() >= self.seconds

mic_volumes_run = False
_mic_volumes:dict[str, int] = {}
_mic_volumes_proc:subprocess.Popen = None
            
def mic_get_volume(id:str)->int:
    if id in _mic_volumes:
        return _mic_volumes[id]
    _mic_volumes[id] = 0
    if _mic_volumes_proc is not None:
        _mic_volumes_proc.stdin.write(f"{json.dumps({"name": "new_mic", "data": {"id": id}})}\n")
        _mic_volumes_proc.stdin.flush()
    return 0

def mic_volume_background_runner(host:str, secure:bool):
    global _mic_volumes_proc
    _mic_volumes_proc = proc = subprocess.Popen([sys.executable, MIC_VOLUME_PROC_FILE, f"http{"s"*secure}://{host}"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        while mic_volumes_run:
            line = proc.stdout.readline()
            if not line:
                return
            instruction:dict[str] = json.loads(line)
            name:str = instruction["name"]
            data = instruction["data"]
            if name == "change_volume":
                mic_id:str = data["id"]
                volume:int = data["volume"]
                _mic_volumes[mic_id] = volume
    finally:
        proc.terminate()
        proc.wait(0.5)
        proc.kill()

class MicActivityCondition(EventCondition):
    """Condition that is met when microphone activity is above/below/between a desired volume (measured in rms)."""
    CATEGORY_NAME = CONDITION_CATEGORY_MIC_ACTIVITY

    def __init__(self, mic_id:str, above:int|None=None, below:int|None=None, **data):
        data["mic_id"] = mic_id
        if above is not None:
            data["above"] = above
        if below is not None:
            data["below"] = below
        assert isinstance(self.CATEGORY_NAME, str), f"EventCondition {type(self).__name__} must define a CATEGORY_TYPE, got {self.CATEGORY_NAME}"
        super().__init__(self.CATEGORY_NAME, data)

    @property
    def mic_id(self)->str:
        return self.data["mic_id"]

    @mic_id.setter
    def mic_id(self, value:str):
        self.data["mic_id"] = value

    @property
    def above(self)->int:
        return self.data.get("above")

    @above.setter
    def above(self, value:int):
        self.data["above"] = value

    @above.deleter
    def above(self):
        if "above" in self.data:
            del self.data["above"]
    
    @property
    def below(self)->int:
        return self.data.get("below")

    @below.setter
    def below(self, value:int):
        self.data["below"] = value

    @below.deleter
    def below(self):
        if "below" in self.data:
            del self.data["below"]

    def handle(self, negotiator:"EventNegotiator", event:"Event")->bool:
        a = self.above
        b = self.below
        volume:int = mic_get_volume(self.mic_id)
        return (a is None or volume >= a) and (b is None or volume <= b)
    

EVENT_CONDITION_TYPES:dict[str, type[EventCondition]] = {
    CONDITION_CATEGORY_STATE_MATCH: StateMatchCondition,
    CONDITION_CATEGORY_MEDIA_MATCH: MediaMatchCondition,
    CONDITION_CATEGORY_KEYBINDS_IDLE: IdleCondition,
    CONDITION_CATEGORY_ACTIVE_LIMIT: ActiveLimitCondition,
    CONDITION_CATEGORY_INACTIVE: InactiveCondition
}

EventConditions = list[EventCondition]

class Event:
    def __init__(self, name:str, media:MediaReference, conditions:EventConditions):
        self.name = name
        self.media = media
        self.conditions = conditions

    def __getstate__(self):
        rtv:dict[str] = {"media": self.media.__getstate__(), "conditions": [condition.__getstate__() for condition in self.conditions]}
        return rtv

    def __setstate__(self, d:dict[str]):
        if "name" in d:
            self.name:str = d["name"]
        self.media = MediaReference.__new__(MediaReference)
        self.media.__setstate__(d["media"])
        conditions = []
        cd:list[dict] = d["conditions"]
        for cinfo in cd:
            c = EventCondition.__new__(EventCondition)
            c.__setstate__(cinfo)
            conditions.append(c)
        self.conditions = conditions

    def state_name(self):
        return f"event:{self.name}:{hex(hash(self.name))[2:]}" #hash prevents name collisions with a state named f"event:{self.name}"

StateCollection = dict[str, State]
TransitionStructure = dict[str, list[Transition]]
EventCollection = dict[str, Event]

class StateMap:
    @classmethod
    def loads(cls, s:str|bytes, **kwargs):
        d = json.loads(s, **kwargs)
        statemap = cls.__new__(cls)
        statemap.__setstate__(d)
        return statemap

    @classmethod
    def load(cls, f:io.IOBase, **kwargs):
        d = json.load(f, **kwargs)
        statemap = cls.__new__(cls)
        statemap.__setstate__(d)
        return statemap

    def __init__(self, states:StateCollection=None, transitions:TransitionStructure=None, events:EventCollection=None):
        self.states = {} if states is None else states
        self.transitions = {} if transitions is None else transitions
        self.events = {} if events is None else events

    def __getstate__(self):
        return {
            "states": {name: state.__getstate__() for name, state in self.states.items()},
            "transitions": {name: [t.__getstate__() for t in ts] for name, ts in self.transitions.items()},
            "events": {name: event.__getstate__() for name, event in self.events.items()}
        }

    def __setstate__(self, d:dict[str]):
        states = {}
        transitions = {}
        events = {}

        dstates:dict[str, dict] = d.get("states", None)
        dtransitions:dict[str, list] = d.get("transitions", None)
        devents = d.get("events", None)

        if isinstance(dstates, dict):
            for name, info in dstates.items():
                state = State.__new__(State)
                state.__setstate__(info)
                state.name = name
                states[name] = state
        if isinstance(dtransitions, dict):
            for name, info in dtransitions.items():
                ts = []
                for t in info:
                    transition = Transition.__new__(Transition)
                    transition.__setstate__(t)
                    ts.append(transition)
                transitions[name] = ts
        if isinstance(devents, dict):
            for name, info in devents.items():
                info["name"] = name
                event = Event.__new__(Event)
                event.__setstate__(info)
                events[name] = event
        self.__init__(states, transitions, events)


    def dumps(self, **kwargs):
        return json.dumps(self.__getstate__(), **kwargs)

    def dump(self, f:io.IOBase, **kwargs):
        json.dump(self.__getstate__(), f, **kwargs)

RemoveCallback = Callable[[], None]

class NavigatorStackFrame:

    __slots__ = "state", "transitions", "prev", "keybinds"

    def __init__(self, state:State, transitions:list[Transition], prev:Self=None):
        self.state = state
        self.transitions = transitions
        self.prev = prev
        self.keybinds:set[RemoveCallback] = set()

OnPushCallback = Callable[[NavigatorStackFrame|None, NavigatorStackFrame], None]
OnPopCallback = Callable[[NavigatorStackFrame, NavigatorStackFrame|None], None]
OnChangeCallback = Callable[[NavigatorStackFrame, NavigatorStackFrame], None]

class StateMapNavigator:
    def __init__(self, statemap:StateMap, default_state:str|None=None, on_push:OnPushCallback=None, on_pop:OnPopCallback=None, on_change:OnChangeCallback=None):
        self.statemap = statemap
        self.default_state = default_state
        self.stack:NavigatorStackFrame = None
        self._stack_length = 0

        self.on_push = on_push
        self.on_pop = on_pop
        self.on_change = on_change

        self.lock = threading.Lock()

    def __len__(self):
        return self._stack_length

    def bind_frame(self, frame:NavigatorStackFrame):
        for t in frame.transitions:
            rm_callback = None
            if t.mode == TransitionMode.HOLD:
                rm_callback = self.hook_mode_hold(frame, t)
            elif t.mode == TransitionMode.TRIGGER_DOWN:
                rm_callback = self.hook_mode_down(frame, t)
            elif t.mode == TransitionMode.TRIGGER_UP:
                rm_callback = self.hook_mode_up(frame, t)
            
            if rm_callback is not None:
                frame.keybinds.add(rm_callback)

    def unbind_frame(self, frame:NavigatorStackFrame):
        for kb in frame.keybinds:
            kb() #function that removes keybind
        frame.keybinds.clear()

    def push(self, state_name:str):
        with self.lock:
            state = self.statemap.states[state_name]
            transitions = self.statemap.transitions.get(state_name, [])
            prev = self.stack
            self.stack = NavigatorStackFrame(state, transitions, prev=prev)
            self._stack_length += 1
            if prev is not None:
                self.unbind_frame(prev)
            self.bind_frame(self.stack)
            if self.on_push is not None:
                self.on_push(self.stack.prev, self.stack)
            return self.stack

    def pop(self):
        with self.lock:
            old = self.stack
            self.unbind_frame(old)
            self.stack = self.stack.prev
            self._stack_length -= 1
            if self.stack is not None:
                self.bind_frame(self.stack)
            if self.on_pop is not None:
                self.on_pop(old, self.stack)
            return self.stack

    def change(self, state_name:str):
        with self.lock:
            state = self.statemap.states[state_name]
            transitions = self.statemap.transitions.get(state_name, [])
            self.unbind_frame(self.stack)
            old = self.stack
            self.stack = NavigatorStackFrame(state, transitions, prev=self.stack.prev)
            self.bind_frame(self.stack)
            if self.on_change is not None:
                self.on_change(old, self.stack)
            return self.stack

    def init_default(self):
        if self.stack is None and self.default_state is not None:
            self.push(self.default_state)

    def hook_mode_hold(self, frame:NavigatorStackFrame, t:Transition)->RemoveCallback|None:
        raise NotImplementedError
    
    def hook_mode_down(self, frame:NavigatorStackFrame, t:Transition)->RemoveCallback|None:
        raise NotImplementedError
    
    def hook_mode_up(self, frame:NavigatorStackFrame, t:Transition)->RemoveCallback|None:
        raise NotImplementedError
    
    def event_can_interrupt(self):
        return self.stack is None or self.stack.state.allow_event_interrupt
    
EventActiveState = tuple[bool, datetime] #active|inactive, begin_time

class EventQueueNode:
    __slots__ = "event", "next"
    def __init__(self, event:Event, next:Self|None=None):
        self.event = event
        self.next = next

class EventQueue:
    __slots__ = "_head", "_tail", "_event_set"
    def __init__(self, head:EventQueueNode|None=None, tail:EventQueueNode|None=None):
        self._head = node = head
        if tail is None:
            if node is None:
                self._tail = None
            else:
                while node.next is not None:
                    node = node.next
                self._tail = node
        else:
            self._tail = tail
        self._event_set:set[str] = set()

    def __contains__(self, event:str|Event):
        return (event.name if isinstance(event, Event) else event) in self._event_set

    def __iter__(self):
        node = self._head
        while node is not None:
            yield node.event
            node = node.next

    def enqueue(self, event:Event):
        self._event_set.add(event.name)
        node = EventQueueNode(event)
        if self._tail is None: #tail is None, head is None
            self._head = node
            self._tail = node
        else:
            self._tail.next = node
            self._tail = node

    def dequeue(self)->Event|None:
        if self._head is None: #head is None, tail is None
            return None
        node = self._head
        self._head = self._head.next
        if self._head is None:
            self._tail = None
        self._event_set.remove(node.event.name)
        return node.event
    
    def skip(self, event:str|Event, n:int=-1)->int:
        name = event.name if isinstance(event, Event) else event
        if name not in self._event_set:
            return 0
        self._event_set.remove(name)
        count = 0
        while self._head is not None and self._head.event.name == name:
            self._head = self._head.next
            count += 1
            if count == n:
                return count
        if self._head is None or self._head.next is None:
            self._tail = self._head
            return count
        node = self._head
        lookahead = node.next.next
        while lookahead is not None:
            if node.next.event.name == name:
                node.next = lookahead
                lookahead = lookahead.next
                count += 1
                if count == n:
                    return count
                elif lookahead is None:
                    break
            node = node.next
            lookahead = lookahead.next
        self._tail = node if node.next.event.name == name else node.next
        return count

    def peek(self)->Event|None:
        if self._head is None:
            return None
        return self._head.event

class EventNegotiator:
    def __init__(self, navstack_callback:Callable[[], NavigatorStackFrame|None], statemap_callback:Callable[[], StateMap], activity_update_callback:Callable[[], None]|None=None):
        self.navstack_callback = navstack_callback
        self.statemap_callback = statemap_callback
        self.activity_update_callback = activity_update_callback
        self.last_keybind_trigger = datetime.now(timezone.utc)
        self.keybind_holding = False
        self.event_activity_states:dict[str, EventActiveState] = {}
        self.active_queue = EventQueue()
        self.__activity_state_default = datetime.now(timezone.utc)
        self.wait_flag = threading.Event()
        self.background_task_wait_interval = 0.1
        self.keep_running = True
        self._update_lock = threading.Lock()

    def get_first_active(self):
        return self.active_queue.peek()
    
    def check_event(self, event:Event)->bool:
        if not event.conditions:
            return False
        is_active = True
        some_success = False
        for condition in event.conditions:
            try:
                condition_type = EVENT_CONDITION_TYPES.get(condition.name,None)
                if condition_type is None:
                    continue
                condition = condition_type.cast(condition)
                is_active &= condition.handle(self, event)
                some_success = True
            except Exception as e:
                traceback.print_exception(e)
        return some_success and is_active
    
    def update_event_activity(self):
        with self._update_lock:
            statemap = self.statemap_callback()
            if statemap is None:
                return
            any_changes = False
            for event in statemap.events.values():
                is_active = self.check_event(event)
                state = self.event_activity_states.get(event.name, None)
                newstate = None
                if state is None:
                    if is_active:
                        newstate = self.event_activity_states[event.name] = is_active, datetime.now(timezone.utc)
                else:
                    active, _ = state
                    if is_active != active:
                        newstate = self.event_activity_states[event.name] = is_active, datetime.now(timezone.utc)
                
                if newstate is not None:
                    any_changes = True
                    if is_active:
                        if event not in self.active_queue:
                            self.active_queue.enqueue(event)
                    else:
                        self.active_queue.skip(event)
            
            if any_changes and self.activity_update_callback:
                self.activity_update_callback()

    def background_task(self):
        while self.keep_running:
            self.update_event_activity()
            if self.wait_flag.wait(self.background_task_wait_interval):
                self.wait_flag.clear()