from datetime import timedelta
from enum import Enum
import io
import json
import threading
from typing import Callable, Self

STATEMAP_FILE = "png_binds.json"

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

CONDITION_CATEGORY_STATE_MATCH = "state_match"
CONDITION_CATEGORY_MEDIA_MATCH = "media_match"
CONDITION_CATEGORY_KEYBINDS_IDLE = "keybinds_idle"
CONDITION_CATEGORY_ACTIVE_LIMIT = "active_limit"
CONDITION_CATEGORY_INACTIVE = "inactive"

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


class DurationConditionType(EventCondition):
    """Type of conditions which stores a timespan in seconds."""
    CATEGORY_NAME:str = NotImplemented
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

class ActiveLimitCondition(DurationConditionType):
    """Condition that is not met when all of an event's conditions have been met for more than the given amount of seconds."""
    CATEGORY_NAME = CONDITION_CATEGORY_ACTIVE_LIMIT

class InactiveCondition(DurationConditionType):
    """Condition that is met when all of an event's conditions haven't been met for more than the given amount of seconds."""
    CATEGORY_NAME = CONDITION_CATEGORY_INACTIVE


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


class NavigatorStackFrame:

    __slots__ = "state", "transitions", "prev", "keybinds"

    def __init__(self, state:State, transitions:list[Transition], prev:Self=None):
        self.state = state
        self.transitions = transitions
        self.prev = prev
        self.keybinds:set[Callable[[], None]] = set()

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

    def hook_mode_hold(frame:NavigatorStackFrame, t:Transition):
        raise NotImplementedError
    
    def hook_mode_down(frame:NavigatorStackFrame, t:Transition):
        raise NotImplementedError
    
    def hook_mode_up(frame:NavigatorStackFrame, t:Transition):
        raise NotImplementedError
    
    def event_can_interrupt(self):
        return self.stack is None or self.stack.state.allow_event_interrupt