from datetime import timedelta
from enum import Enum
import io
import json
import keyboard
import threading
import time
from typing import Callable, Self
import weakref


class TransitionMode(Enum):
    HOLD = 1
    TRIGGER_DOWN = 2
    TRIGGER_UP = 3

TimeoutChange = tuple[str, timedelta] #change to the specified state after the given timeout

class State:
    def __init__(self, name:str, media_path:str, change:TimeoutChange=None):
        self.name = name
        self.media_path = media_path
        self.change = change

    def __getstate__(self):
        rtv:dict[str] = {"media_path": self.media_path}
        if self.change is not None:
            rtv["change"] = {
                "destination": self.change[0],
                "timeout": self.change[1]
            }
        return rtv

    def __setstate__(self, d:dict[str]):
        if "name" in d:
            self.name = d["name"]
        self.media_path = d["media_path"]
        dchange = d.get("change", None)
        if isinstance(dchange, dict):
            self.change = dchange["desitnation"], dchange["timeout"]
        else:
            self.change = None

class Transition:
    def __init__(self, keybind:str, mode:TransitionMode, destination:str, pop_destination:str=None):
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
        dtransitions:dict[str, dict] = d.get("transitions", None)

        if isinstance(dstates, dict):
            for name, info in dstates.items():
                state = State.__new__(State)
                state.__setstate__(info)
                state.name = name
                states[name] = state
        if isinstance(dtransitions, dict):
            for name, info in dtransitions.items():
                transition = Transition.__new__(Transition)
                transition.__setstate__(info)
                transitions[name] = transition
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


class StateMapNavigator:
    def __init__(self, statemap:StateMap, default_state:str, on_push:Callable[[NavigatorStackFrame|None, NavigatorStackFrame], None]=None, on_pop:Callable[[NavigatorStackFrame, NavigatorStackFrame|None], None]=None, on_change:Callable[[NavigatorStackFrame, NavigatorStackFrame], None]=None):
        self.statemap = statemap
        self.default_state = default_state
        self.stack:NavigatorStackFrame = None
        self._stack_length = 0

        self.on_push = on_push
        self.on_pop = on_pop
        self.on_change = on_change

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
        if self.stack is None:
            self.push(self.default_state)

    def hook_mode_hold(self, frame:NavigatorStackFrame, t:Transition):
        flag = threading.Event()
        do_popstate = False

        def on_up():
            while not flag.is_set():
                if keyboard.is_pressed(t.keybind):
                    flag.wait(0.05)
                else:
                    flag.set()
            
            navthread.join()

            self.pop()
            if do_popstate and t.pop_destination is not None:
                frame = self.stack
                state = self.statemap.states[t.pop_destination]
                while state.change is not None and self.stack == frame:
                    name, duration = state.change
                    if self.stack.state != state:
                        frame = self.change(state.name)
                    time.sleep(duration.total_seconds())
                    state = self.statemap.states[name]
                if self.stack == frame and state != self.stack.state:
                    self.change(state.name)

        def navigate_state_changes():
            nonlocal do_popstate
            frame = self.stack
            state = self.statemap.states[t.destination]
            while not flag.is_set() and state.change is not None and self.stack == frame:
                name, duration = state.change
                if self.stack.state != state:
                    frame = self.change(state.name)
                if flag.wait(duration.total_seconds()):
                    break
                else:
                    state = self.statemap.states[name]
            
            if not flag.is_set() and self.stack == frame:
                if state != self.stack.state:
                    frame = self.change(state.name)
                do_popstate = True


        upthread = threading.Thread(target=on_up, daemon=True)
        navthread = threading.Thread(target=navigate_state_changes, daemon=True)

        def on_down():
            self.push(t.destination) #on_down hotkey is removed
            navthread.start()
            upthread.start()

        return keyboard.add_hotkey(t.keybind, on_down)

    def hook_mode_down(self, frame:NavigatorStackFrame, t:Transition):
        def navigate_state_changes():
            frame = self.stack
            state = self.statemap.states[t.destination]
            while state.change is not None and self.stack == frame:
                name, duration = state.change
                if self.stack.state != state:
                    frame = self.change(state.name)
                time.sleep(duration.total_seconds())
                state = self.statemap.states[name]
            if self.stack == frame and state != self.stack.state:
                self.change(state.name)

        downthread = threading.Thread(target=navigate_state_changes, daemon=True)

        def on_down():
            downthread.start()

        return keyboard.add_hotkey(t.keybind, on_down)

    def hook_mode_up(self, frame:NavigatorStackFrame, t:Transition):
        def navigate_state_changes():
            frame = self.stack
            state = self.statemap.states[t.destination]
            while state.change is not None and self.stack == frame:
                name, duration = state.change
                if self.stack.state != state:
                    frame = self.change(state.name)
                time.sleep(duration.total_seconds())
                state = self.statemap.states[name]
            if self.stack == frame and state != self.stack.state:
                self.change(t.destination)

        upthread = threading.Thread(target=navigate_state_changes, daemon=True)

        def on_up():
            upthread.start()

        return keyboard.add_hotkey(t.keybind, on_up, trigger_on_release=True)
