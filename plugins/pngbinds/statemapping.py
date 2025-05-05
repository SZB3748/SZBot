from datetime import timedelta
from enum import Enum
import io
import json
import threading
from typing import Callable, Self
import weakref

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
    def __init__(self, name:str, media:MediaReference, change:TimeoutChange=None):
        self.name = name
        self.media = media
        self.change = change

    def __eq__(self, other):
        if isinstance(other, State):
            return self is other or self.name == other.name
        return super().__eq__(other)
    
    def __hash__(self):
        return hash(str(id(type(self))) + self.name)

    def __getstate__(self):
        rtv:dict[str] = {"media": self.media.__getstate__()}
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

StateCollection = dict[str, State]
TransitionStructure = dict[str, list[Transition]]

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

    def __init__(self, states:StateCollection=None, transitions:TransitionStructure=None):
        self.states = {} if states is None else states
        self.transitions = {} if transitions is None else transitions

    def __getstate__(self):
        return {
            "states": {name: state.__getstate__() for name, state in self.states.items()},
            "transitions": {name: [t.__getstate__() for t in ts] for name, ts in self.transitions.items()}
        }

    def __setstate__(self, d:dict[str]):
        states = {}
        transitions = {}

        dstates:dict[str, dict] = d.get("states", None)
        dtransitions:dict[str, list] = d.get("transitions", None)

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
        self.__init__(states, transitions)


    def dumps(self, **kwargs):
        return json.dumps(self.__getstate__(), **kwargs)

    def dump(self, f:io.IOBase, **kwargs):
        json.dump(self.__getstate__(), f, **kwargs)


class NavigatorStackFrame:

    __slots__ = "_state", "transitions", "prev", "keybinds"

    def __init__(self, state:State, transitions:list[Transition], prev:Self=None):
        self.state = state
        self.transitions = transitions
        self.prev = prev
        self.keybinds:set[Callable[[], None]] = set()

    @property
    def state(self):
        return self._state()

    @state.setter
    def state(self, value:State):
        self._state = weakref.ref(value)

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