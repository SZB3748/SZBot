import json
import keyboard
import statemapping
import sys
import threading
import time
import websocket

class KeyboardStateMapNavigator(statemapping.StateMapNavigator):
    def hook_mode_hold(self, frame:statemapping.NavigatorStackFrame, t:statemapping.Transition):
        flag = threading.Event()
        do_popstate = False

        def on_up():
            not_sent_unhold = True
            try:
                while not flag.is_set():
                    if keyboard.is_pressed(t.keybind):
                        flag.wait(0.05)
                    else:
                        flag.set()
            
                navthread.join()
                send_keypress(t.keybind, t.mode, hold_start=False)
                not_sent_unhold = False

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
            except (KeyboardInterrupt, SystemExit):
                flag.set()
            finally:
                if not_sent_unhold:
                    send_keypress(t.keybind, t.mode, hold_start=False)

        def navigate_state_changes():
            nonlocal do_popstate
            frame = self.stack
            state = self.statemap.states[t.destination]
            try:
                while not flag.is_set() and state.change is not None and self.stack == frame:
                    name, duration = state.change
                    if self.stack.state != state:
                        frame = self.change(state.name)
                    if flag.wait(duration.total_seconds()):
                        break
                    else:
                        state = self.statemap.states[name]
            except (KeyboardInterrupt, SystemExit):
                flag.set()
            
            if not flag.is_set() and self.stack == frame:
                if state != self.stack.state:
                    frame = self.change(state.name)
                do_popstate = True


        upthread = threading.Thread(target=on_up, daemon=True)
        navthread = threading.Thread(target=navigate_state_changes, daemon=True)

        def on_down():
            send_keypress(t.keybind, t.mode, hold_start=True)
            self.push(t.destination) #on_down hotkey is removed
            navthread.start()
            upthread.start()

        return keyboard.add_hotkey(t.keybind, on_down)

    def hook_mode_down(self, frame:statemapping.NavigatorStackFrame, t:statemapping.Transition):
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
            send_keypress(t.keybind, t.mode)
            downthread.start()

        return keyboard.add_hotkey(t.keybind, on_down)

    def hook_mode_up(self, frame:statemapping.NavigatorStackFrame, t:statemapping.Transition):
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
            send_keypress(t.keybind, t.mode)
            upthread.start()

        return keyboard.add_hotkey(t.keybind, on_up, trigger_on_release=True)

def handle_socket_event(name:str, data:dict[str]):
    global nav
    if name == "nav_init":
        statemap = statemapping.StateMap.__new__(statemapping.StateMap)
        statemap.__setstate__(data["statemap"])
        nav = KeyboardStateMapNavigator(statemap, data.get("default_state", None), on_push=on_push, on_pop=on_pop, on_change=on_change)
        nav.init_default()
        send_stack()
    elif name == "stack_update":
        stackdata = data.get("stack",None)
        if isinstance(stackdata, list):
            if nav.stack is not None:
                nav.unbind_frame(nav.stack)
            nav.stack = data_to_stack(stackdata, nav.statemap)
            nav.bind_frame(nav.stack)
    elif name == "statemap_update":
        statemap = statemapping.StateMap.__new__(statemapping.StateMap)
        statemap.__setstate__(data["statemap"])
        if nav.stack is not None:
            nav.unbind_frame(nav.stack)
            frame = nav.stack
            while frame is not None:
                frame.state = statemap.states[frame.state.name]
                frame.transitions = statemap.transitions.get(frame.state.name, [])
                frame = frame.prev
            nav.bind_frame(nav.stack)
        nav.statemap = statemap
    elif name == "default_state_update":
        name:str|None = data.get("name", None)
        if name is None or isinstance(name, str):
            nav.default_state = name
    elif name == "cleanup":
        if nav.stack is not None:
            nav.unbind_frame(nav.stack)
            nav.stack = None
        ws.close()
    else:
        print("pngbinds:\tbad event", name, data)

def on_open(ws:websocket.WebSocket):
    print("pngbinds:\tclient connected")

def on_message(ws:websocket.WebSocket, msg):
    if isinstance(msg, (str, bytes)):
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            print("pngbinds:\tclient received invalid JSON:", msg)
        else:
            if isinstance(data, dict) and isinstance((event_name := data.get("name", None)), str):
                handle_socket_event(event_name, data.get("data"))

def stack_to_data(stack:statemapping.NavigatorStackFrame|None)->list[str|None]:
    frames = []
    while stack is not None:
        frames.append(stack.state.name)
        stack = stack.prev
    return frames

def data_to_stack(data:list[str|None])->statemapping.NavigatorStackFrame|None:
    stack = None
    for framestate in reversed(data):
        state = nav.statemap.states.get(framestate, None)
        transitions = nav.statemap.transitions.get(framestate, [])
        stack = statemapping.NavigatorStackFrame(state, transitions, stack)
    return stack

def send_stack(name:str="stack_update"):
    ev = {
        "name": name,
        "data": {
            "stack": stack_to_data(nav.stack)
        }
    }
    ws.send(json.dumps(ev))

def send_keypress(keybind:str, mode:statemapping.TransitionMode, hold_start:bool=None, name:str="key_press"):
    ev = {
        "name": name,
        "data": {
            "keybind": keybind,
            "mode": mode.value,
            "hold_start": hold_start
        }
    }
    ws.send(json.dumps(ev))

def on_push(old:statemapping.NavigatorStackFrame|None, new:statemapping.NavigatorStackFrame):
    send_stack()
    print(f"pngbinds:\t{None if old is None else old.state.name} >> {new.state.name}")
    for t in new.transitions:
        print(f"pngbinds:\t{t.keybind} {t.mode.name} --> {repr(t.destination)}{"" if t.pop_destination is None else ".."+repr(t.pop_destination)}")

def on_pop(old:statemapping.NavigatorStackFrame, new:statemapping.NavigatorStackFrame|None):
    send_stack()
    print(f"pngbinds:\t{None if new is None else new.state.name} << {old.state.name}")
    if new is not None:
        for t in new.transitions:
            print(f"pngbinds:\t{t.keybind} {t.mode.name} --> {repr(t.destination)}{"" if t.pop_destination is None else ".."+repr(t.pop_destination)}")

def on_change(old:statemapping.NavigatorStackFrame, new:statemapping.NavigatorStackFrame):
    send_stack()
    print(f"pngbinds:\t{old.state.name} -> {new.state.name}")
    for t in new.transitions:
        print(f"pngbinds:\t{t.keybind} {t.mode.name} --> {repr(t.destination)}{"" if t.pop_destination is None else ".."+repr(t.pop_destination)}")


nav:KeyboardStateMapNavigator = None
ws = websocket.WebSocketApp(sys.argv[1], on_open=on_open, on_message=on_message)

if __name__ == "__main__":
    ws.run_forever()