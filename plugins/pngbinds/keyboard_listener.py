from datetime import datetime, timezone
import json
import pynput
import re
import statemapping
import sys
import threading
import time
from typing import Callable
from uuid import UUID, uuid4
import websocket

KEYBIND_PATTERN = re.compile(r"[ ]*((?:(?:[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*|\([ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*\)[ ]*)|(?:\([ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*(?:\+[ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*)\)[ ]*))(?:\+[ ]*(?:(?:[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*|\([ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*\)[ ]*)|(?:\([ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*(?:\+[ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*)\)[ ]*)))*)(?:\+[ ]*)*")
KEYBIND_SPLIT_PATTERN = re.compile(r"\+(?![^()]*\))")

_PYNPUT_KEY_NAMES = {
    "alt": pynput.keyboard.Key.alt,

    "alt left": pynput.keyboard.Key.alt_l,
    "left alt": pynput.keyboard.Key.alt_l,
    "l alt":pynput.keyboard.Key.alt_l,
    "alt l":pynput.keyboard.Key.alt_l,

    "alt right": pynput.keyboard.Key.alt_r,
    "right alt": pynput.keyboard.Key.alt_r,
    "r alt":pynput.keyboard.Key.alt_r,
    "alt r":pynput.keyboard.Key.alt_r,

    "windows": pynput.keyboard.Key.cmd,
    "window": pynput.keyboard.Key.cmd,
    "win": pynput.keyboard.Key.cmd,

    "left windows": pynput.keyboard.Key.cmd_l,
    "left window": pynput.keyboard.Key.cmd_l,
    "left win": pynput.keyboard.Key.cmd_l,
    "windows left": pynput.keyboard.Key.cmd_l,
    "window left": pynput.keyboard.Key.cmd_l,
    "win left": pynput.keyboard.Key.cmd_l,
    "l windows": pynput.keyboard.Key.cmd_l,
    "l window": pynput.keyboard.Key.cmd_l,
    "l win": pynput.keyboard.Key.cmd_l,
    "windows l": pynput.keyboard.Key.cmd_l,
    "window l": pynput.keyboard.Key.cmd_l,
    "win l": pynput.keyboard.Key.cmd_l,
    
    "right windows": pynput.keyboard.Key.cmd_r,
    "right window": pynput.keyboard.Key.cmd_r,
    "right win": pynput.keyboard.Key.cmd_r,
    "windows right": pynput.keyboard.Key.cmd_r,
    "window right": pynput.keyboard.Key.cmd_r,
    "win right": pynput.keyboard.Key.cmd_r,
    "r windows": pynput.keyboard.Key.cmd_r,
    "r window": pynput.keyboard.Key.cmd_r,
    "r win": pynput.keyboard.Key.cmd_r,
    "windows r": pynput.keyboard.Key.cmd_r,
    "window r": pynput.keyboard.Key.cmd_r,
    "win r": pynput.keyboard.Key.cmd_r,

    "command": pynput.keyboard.Key.cmd,
    "cmd": pynput.keyboard.Key.cmd,

    "left command": pynput.keyboard.Key.cmd_l,
    "left cmd": pynput.keyboard.Key.cmd_l,
    "command left": pynput.keyboard.Key.cmd_l,
    "cmd left": pynput.keyboard.Key.cmd_l,
    "l command": pynput.keyboard.Key.cmd_l,
    "l cmd": pynput.keyboard.Key.cmd_l,
    "command l": pynput.keyboard.Key.cmd_l,
    "cmd l": pynput.keyboard.Key.cmd_l,
    
    "right command": pynput.keyboard.Key.cmd_r,
    "right cmd": pynput.keyboard.Key.cmd_r,
    "command right": pynput.keyboard.Key.cmd_r,
    "cmd right": pynput.keyboard.Key.cmd_r,
    "r command": pynput.keyboard.Key.cmd_r,
    "r cmd": pynput.keyboard.Key.cmd_r,
    "command r": pynput.keyboard.Key.cmd_r,
    "cmd r": pynput.keyboard.Key.cmd_r,

    "super": pynput.keyboard.Key.cmd,
    "sup": pynput.keyboard.Key.cmd,

    "left super": pynput.keyboard.Key.cmd_l,
    "left sup": pynput.keyboard.Key.cmd_l,
    "super left": pynput.keyboard.Key.cmd_l,
    "sup left": pynput.keyboard.Key.cmd_l,
    "l super": pynput.keyboard.Key.cmd_l,
    "l sup": pynput.keyboard.Key.cmd_l,
    "super l": pynput.keyboard.Key.cmd_l,
    "sup l": pynput.keyboard.Key.cmd_l,
    
    "right super": pynput.keyboard.Key.cmd_r,
    "right sup": pynput.keyboard.Key.cmd_r,
    "super right": pynput.keyboard.Key.cmd_r,
    "sup right": pynput.keyboard.Key.cmd_r,
    "r super": pynput.keyboard.Key.cmd_r,
    "r sup": pynput.keyboard.Key.cmd_r,
    "super r": pynput.keyboard.Key.cmd_r,
    "sup r": pynput.keyboard.Key.cmd_r,

    "ctrl": pynput.keyboard.Key.ctrl,

    "ctrl left": pynput.keyboard.Key.ctrl_l,
    "left ctrl": pynput.keyboard.Key.ctrl_l,
    "l ctrl":pynput.keyboard.Key.ctrl_l,
    "ctrl l":pynput.keyboard.Key.ctrl_l,

    "ctrl right": pynput.keyboard.Key.ctrl_r,
    "right ctrl": pynput.keyboard.Key.ctrl_r,
    "r ctrl":pynput.keyboard.Key.ctrl_r,
    "ctrl r":pynput.keyboard.Key.ctrl_r,

    "shift": pynput.keyboard.Key.shift,

    "shift left": pynput.keyboard.Key.shift_l,
    "left shift": pynput.keyboard.Key.shift_l,
    "l shift":pynput.keyboard.Key.shift_l,
    "shift l":pynput.keyboard.Key.shift_l,

    "shift right": pynput.keyboard.Key.shift_r,
    "right shift": pynput.keyboard.Key.shift_r,
    "r shift":pynput.keyboard.Key.shift_r,
    "shift r":pynput.keyboard.Key.shift_r,

    "down": pynput.keyboard.Key.down,
    "arrow down": pynput.keyboard.Key.down,
    "down arrow": pynput.keyboard.Key.down,

    "up": pynput.keyboard.Key.up,
    "arrow up": pynput.keyboard.Key.up,
    "up arrow": pynput.keyboard.Key.up,
    
    "left": pynput.keyboard.Key.left,
    "arrow left": pynput.keyboard.Key.left,
    "left arrow": pynput.keyboard.Key.left,
    
    "right": pynput.keyboard.Key.right,
    "arrow right": pynput.keyboard.Key.right,
    "right arrow": pynput.keyboard.Key.right,

    "home": pynput.keyboard.Key.home,
    "end": pynput.keyboard.Key.end,

    "page down": pynput.keyboard.Key.page_down,
    "page up": pynput.keyboard.Key.page_up,

    "delete": pynput.keyboard.Key.delete,
    "del": pynput.keyboard.Key.delete,

    "insert": pynput.keyboard.Key.insert,
    
    "enter": pynput.keyboard.Key.enter,

    "backspace": pynput.keyboard.Key.backspace,
    "back space": pynput.keyboard.Key.backspace,

    "capslock": pynput.keyboard.Key.caps_lock,
    "caps lock": pynput.keyboard.Key.caps_lock,

    "numlock": pynput.keyboard.Key.num_lock,
    "num lock": pynput.keyboard.Key.num_lock,

    "scroll lock": pynput.keyboard.Key.scroll_lock,

    "esc": pynput.keyboard.Key.esc,
    "escape": pynput.keyboard.Key.esc,
    
    "space": pynput.keyboard.Key.space,
    
    "tab": pynput.keyboard.Key.tab,

    "f1": pynput.keyboard.Key.f1,
    "f 1": pynput.keyboard.Key.f1,
    "fn1": pynput.keyboard.Key.f1,
    "fn 1": pynput.keyboard.Key.f1,
    "func1": pynput.keyboard.Key.f1,
    "func 1": pynput.keyboard.Key.f1,
    "function1": pynput.keyboard.Key.f1,
    "function 1": pynput.keyboard.Key.f1,

    "f2": pynput.keyboard.Key.f2,
    "f 2": pynput.keyboard.Key.f2,
    "fn2": pynput.keyboard.Key.f2,
    "fn 2": pynput.keyboard.Key.f2,
    "func2": pynput.keyboard.Key.f2,
    "func 2": pynput.keyboard.Key.f2,
    "function2": pynput.keyboard.Key.f2,
    "function 2": pynput.keyboard.Key.f2,
    
    "f3": pynput.keyboard.Key.f3,
    "f 3": pynput.keyboard.Key.f3,
    "fn3": pynput.keyboard.Key.f3,
    "fn 3": pynput.keyboard.Key.f3,
    "func3": pynput.keyboard.Key.f3,
    "func 3": pynput.keyboard.Key.f3,
    "function3": pynput.keyboard.Key.f3,
    "function 3": pynput.keyboard.Key.f3,
    
    "f4": pynput.keyboard.Key.f4,
    "f 4": pynput.keyboard.Key.f4,
    "fn4": pynput.keyboard.Key.f4,
    "fn 4": pynput.keyboard.Key.f4,
    "func4": pynput.keyboard.Key.f4,
    "func 4": pynput.keyboard.Key.f4,
    "function4": pynput.keyboard.Key.f4,
    "function 4": pynput.keyboard.Key.f4,
    
    "f5": pynput.keyboard.Key.f5,
    "f 5": pynput.keyboard.Key.f5,
    "fn5": pynput.keyboard.Key.f5,
    "fn 5": pynput.keyboard.Key.f5,
    "func5": pynput.keyboard.Key.f5,
    "func 5": pynput.keyboard.Key.f5,
    "function5": pynput.keyboard.Key.f5,
    "function 5": pynput.keyboard.Key.f5,
    
    "f6": pynput.keyboard.Key.f6,
    "f 6": pynput.keyboard.Key.f6,
    "fn6": pynput.keyboard.Key.f6,
    "fn 6": pynput.keyboard.Key.f6,
    "func6": pynput.keyboard.Key.f6,
    "func 6": pynput.keyboard.Key.f6,
    "function6": pynput.keyboard.Key.f6,
    "function 6": pynput.keyboard.Key.f6,
    
    "f7": pynput.keyboard.Key.f7,
    "f 7": pynput.keyboard.Key.f7,
    "fn7": pynput.keyboard.Key.f7,
    "fn 7": pynput.keyboard.Key.f7,
    "func7": pynput.keyboard.Key.f7,
    "func 7": pynput.keyboard.Key.f7,
    "function7": pynput.keyboard.Key.f7,
    "function 7": pynput.keyboard.Key.f7,
    
    "f8": pynput.keyboard.Key.f8,
    "f 8": pynput.keyboard.Key.f8,
    "fn8": pynput.keyboard.Key.f8,
    "fn 8": pynput.keyboard.Key.f8,
    "func8": pynput.keyboard.Key.f8,
    "func 8": pynput.keyboard.Key.f8,
    "function8": pynput.keyboard.Key.f8,
    "function 8": pynput.keyboard.Key.f8,
    
    "f9": pynput.keyboard.Key.f9,
    "f 9": pynput.keyboard.Key.f9,
    "fn9": pynput.keyboard.Key.f9,
    "fn 9": pynput.keyboard.Key.f9,
    "func9": pynput.keyboard.Key.f9,
    "func 9": pynput.keyboard.Key.f9,
    "function9": pynput.keyboard.Key.f9,
    "function 9": pynput.keyboard.Key.f9,
    
    "f10": pynput.keyboard.Key.f10,
    "f 10": pynput.keyboard.Key.f10,
    "fn10": pynput.keyboard.Key.f10,
    "fn 10": pynput.keyboard.Key.f10,
    "func10": pynput.keyboard.Key.f10,
    "func 10": pynput.keyboard.Key.f10,
    "function10": pynput.keyboard.Key.f10,
    "function 10": pynput.keyboard.Key.f10,
    
    "f11": pynput.keyboard.Key.f11,
    "f 11": pynput.keyboard.Key.f11,
    "fn11": pynput.keyboard.Key.f11,
    "fn 11": pynput.keyboard.Key.f11,
    "func11": pynput.keyboard.Key.f11,
    "func 11": pynput.keyboard.Key.f11,
    "function11": pynput.keyboard.Key.f11,
    "function 11": pynput.keyboard.Key.f11,
    
    "f12": pynput.keyboard.Key.f12,
    "f 12": pynput.keyboard.Key.f12,
    "fn12": pynput.keyboard.Key.f12,
    "fn 12": pynput.keyboard.Key.f12,
    "func12": pynput.keyboard.Key.f12,
    "func 12": pynput.keyboard.Key.f12,
    "function12": pynput.keyboard.Key.f12,
    "function 12": pynput.keyboard.Key.f12,
    
    "f13": pynput.keyboard.Key.f13,
    "f 13": pynput.keyboard.Key.f13,
    "fn13": pynput.keyboard.Key.f13,
    "fn 13": pynput.keyboard.Key.f13,
    "func13": pynput.keyboard.Key.f13,
    "func 13": pynput.keyboard.Key.f13,
    "function13": pynput.keyboard.Key.f13,
    "function 13": pynput.keyboard.Key.f13,
    
    "f14": pynput.keyboard.Key.f14,
    "f 14": pynput.keyboard.Key.f14,
    "fn14": pynput.keyboard.Key.f14,
    "fn 14": pynput.keyboard.Key.f14,
    "func14": pynput.keyboard.Key.f14,
    "func 14": pynput.keyboard.Key.f14,
    "function14": pynput.keyboard.Key.f14,
    "function 14": pynput.keyboard.Key.f14,
    
    "f15": pynput.keyboard.Key.f15,
    "f 15": pynput.keyboard.Key.f15,
    "fn15": pynput.keyboard.Key.f15,
    "fn 15": pynput.keyboard.Key.f15,
    "func15": pynput.keyboard.Key.f15,
    "func 15": pynput.keyboard.Key.f15,
    "function15": pynput.keyboard.Key.f15,
    "function 15": pynput.keyboard.Key.f15,
    
    "f16": pynput.keyboard.Key.f16,
    "f 16": pynput.keyboard.Key.f16,
    "fn16": pynput.keyboard.Key.f16,
    "fn 16": pynput.keyboard.Key.f16,
    "func16": pynput.keyboard.Key.f16,
    "func 16": pynput.keyboard.Key.f16,
    "function16": pynput.keyboard.Key.f16,
    "function 16": pynput.keyboard.Key.f16,
    
    "f17": pynput.keyboard.Key.f17,
    "f 17": pynput.keyboard.Key.f17,
    "fn17": pynput.keyboard.Key.f17,
    "fn 17": pynput.keyboard.Key.f17,
    "func17": pynput.keyboard.Key.f17,
    "func 17": pynput.keyboard.Key.f17,
    "function17": pynput.keyboard.Key.f17,
    "function 17": pynput.keyboard.Key.f17,
    
    "f18": pynput.keyboard.Key.f18,
    "f 18": pynput.keyboard.Key.f18,
    "fn18": pynput.keyboard.Key.f18,
    "fn 18": pynput.keyboard.Key.f18,
    "func18": pynput.keyboard.Key.f18,
    "func 18": pynput.keyboard.Key.f18,
    "function18": pynput.keyboard.Key.f18,
    "function 18": pynput.keyboard.Key.f18,
    
    "f19": pynput.keyboard.Key.f19,
    "f 19": pynput.keyboard.Key.f19,
    "fn19": pynput.keyboard.Key.f19,
    "fn 19": pynput.keyboard.Key.f19,
    "func19": pynput.keyboard.Key.f19,
    "func 19": pynput.keyboard.Key.f19,
    "function19": pynput.keyboard.Key.f19,
    "function 19": pynput.keyboard.Key.f19,
    
    "f20": pynput.keyboard.Key.f20,
    "f 20": pynput.keyboard.Key.f20,
    "fn20": pynput.keyboard.Key.f20,
    "fn 20": pynput.keyboard.Key.f20,
    "func20": pynput.keyboard.Key.f20,
    "func 20": pynput.keyboard.Key.f20,
    "function20": pynput.keyboard.Key.f20,
    "function 20": pynput.keyboard.Key.f20,

    "media play pause": pynput.keyboard.Key.media_play_pause,
    "media volume mute": pynput.keyboard.Key.media_volume_mute,
    "media volume down": pynput.keyboard.Key.media_volume_down,
    "media volume up": pynput.keyboard.Key.media_volume_up,
    "media previous": pynput.keyboard.Key.media_previous,
    "media next": pynput.keyboard.Key.media_next,

    "pause": pynput.keyboard.Key.pause,
    
    "menu": pynput.keyboard.Key.menu,
    "printscreen": pynput.keyboard.Key.print_screen,
    "print screen": pynput.keyboard.Key.print_screen,

    "num0": pynput.keyboard.KeyCode.from_vk(96, _scan=82),
    "num 0": pynput.keyboard.KeyCode.from_vk(96, _scan=82),
    "numpad0": pynput.keyboard.KeyCode.from_vk(96, _scan=82),
    "numpad 0": pynput.keyboard.KeyCode.from_vk(96, _scan=82),

    "num1": pynput.keyboard.KeyCode.from_vk(97, _scan=79),
    "num 1": pynput.keyboard.KeyCode.from_vk(97, _scan=79),
    "numpad1": pynput.keyboard.KeyCode.from_vk(97, _scan=79),
    "numpad 1": pynput.keyboard.KeyCode.from_vk(97, _scan=79),

    "num2": pynput.keyboard.KeyCode.from_vk(98, _scan=80),
    "num 2": pynput.keyboard.KeyCode.from_vk(98, _scan=80),
    "numpad2": pynput.keyboard.KeyCode.from_vk(98, _scan=80),
    "numpad 2": pynput.keyboard.KeyCode.from_vk(98, _scan=80),

    "num3": pynput.keyboard.KeyCode.from_vk(99, _scan=81),
    "num 3": pynput.keyboard.KeyCode.from_vk(99, _scan=81),
    "numpad3": pynput.keyboard.KeyCode.from_vk(99, _scan=81),
    "numpad 3": pynput.keyboard.KeyCode.from_vk(99, _scan=81),

    "num4": pynput.keyboard.KeyCode.from_vk(100, _scan=75),
    "num 4": pynput.keyboard.KeyCode.from_vk(100, _scan=75),
    "numpad4": pynput.keyboard.KeyCode.from_vk(100, _scan=75),
    "numpad 4": pynput.keyboard.KeyCode.from_vk(100, _scan=75),

    "num5": pynput.keyboard.KeyCode.from_vk(101, _scan=76),
    "num 5": pynput.keyboard.KeyCode.from_vk(101, _scan=76),
    "numpad5": pynput.keyboard.KeyCode.from_vk(101, _scan=76),
    "numpad 5": pynput.keyboard.KeyCode.from_vk(101, _scan=76),

    "num6": pynput.keyboard.KeyCode.from_vk(102, _scan=77),
    "num 6": pynput.keyboard.KeyCode.from_vk(102, _scan=77),
    "numpad6": pynput.keyboard.KeyCode.from_vk(102, _scan=77),
    "numpad 6": pynput.keyboard.KeyCode.from_vk(102, _scan=77),

    "num7": pynput.keyboard.KeyCode.from_vk(103, _scan=71),
    "num 7": pynput.keyboard.KeyCode.from_vk(103, _scan=71),
    "numpad7": pynput.keyboard.KeyCode.from_vk(103, _scan=71),
    "numpad 7": pynput.keyboard.KeyCode.from_vk(103, _scan=71),

    "num8": pynput.keyboard.KeyCode.from_vk(104, _scan=72),
    "num 8": pynput.keyboard.KeyCode.from_vk(104, _scan=72),
    "numpad8": pynput.keyboard.KeyCode.from_vk(104, _scan=72),
    "numpad 8": pynput.keyboard.KeyCode.from_vk(104, _scan=72),

    "num9": pynput.keyboard.KeyCode.from_vk(105, _scan=73),
    "num 9": pynput.keyboard.KeyCode.from_vk(105, _scan=73),
    "numpad9": pynput.keyboard.KeyCode.from_vk(105, _scan=73),
    "numpad 9": pynput.keyboard.KeyCode.from_vk(105, _scan=73),

    "num mult": pynput.keyboard.KeyCode.from_vk(106),
    "numpad mult": pynput.keyboard.KeyCode.from_vk(106),
    "num multiply": pynput.keyboard.KeyCode.from_vk(106),
    "numpad multiply": pynput.keyboard.KeyCode.from_vk(106),

    "num add": pynput.keyboard.KeyCode.from_vk(107),
    "numpad add": pynput.keyboard.KeyCode.from_vk(107),

    "num enter": pynput.keyboard.KeyCode.from_vk(108),
    "numpad enter": pynput.keyboard.KeyCode.from_vk(108),

    "num sub": pynput.keyboard.KeyCode.from_vk(109),
    "numpad sub": pynput.keyboard.KeyCode.from_vk(109),
    "num subtract": pynput.keyboard.KeyCode.from_vk(109),
    "numpad subtract": pynput.keyboard.KeyCode.from_vk(109),

    "num dot": pynput.keyboard.KeyCode.from_vk(110, _scan=83),
    "numpad dot": pynput.keyboard.KeyCode.from_vk(110, _scan=83),
    "num dec": pynput.keyboard.KeyCode.from_vk(110, _scan=83),
    "numpad dec": pynput.keyboard.KeyCode.from_vk(110, _scan=83),
    "num decimal": pynput.keyboard.KeyCode.from_vk(110, _scan=83),
    "numpad decimal": pynput.keyboard.KeyCode.from_vk(110, _scan=83),
    "num period": pynput.keyboard.KeyCode.from_vk(110, _scan=83),
    "numpad period": pynput.keyboard.KeyCode.from_vk(110, _scan=83),
    "num .": pynput.keyboard.KeyCode.from_vk(110, _scan=83),
    "numpad .": pynput.keyboard.KeyCode.from_vk(110, _scan=83),

    "num div": pynput.keyboard.KeyCode.from_vk(111),
    "numpad div": pynput.keyboard.KeyCode.from_vk(111),
    "num divide": pynput.keyboard.KeyCode.from_vk(111),
    "numpad divide": pynput.keyboard.KeyCode.from_vk(111)
}

AnyKey = pynput.keyboard.Key|pynput.keyboard.KeyCode
Keybind = list[list[AnyKey]]

def parse_keybind_string(s:str)->Keybind|None:
    pth_c = 0
    for c in s:
        if c == "(":
            pth_c += 1
        elif c == ")":
            pth_c -= 1
            if pth_c < 0:
                return None #unmatched )
    if pth_c > 0:
        return None #unmatched (
    
    m = KEYBIND_PATTERN.match(s)
    if m is None:
        return None
    g1 = m.group(1)
    if not isinstance(g1, str):
        return None
    
    rtv:Keybind = []
    for group in KEYBIND_SPLIT_PATTERN.split(g1):
        order = []
        for name in (name.strip() for name in group.strip(" ()").split("+")):
            key = _PYNPUT_KEY_NAMES.get(name,None)
            if key is None:
                if len(name) > 1:
                    return None
                order.append(pynput.keyboard.KeyCode.from_char(name))
            else:
                order.append(key)
        if order:
            rtv.append(order)
    return rtv


class KeyboardStateMapNavigator(statemapping.StateMapNavigator):
    def hook_mode_hold(self, frame:statemapping.NavigatorStackFrame, t:statemapping.Transition):
        parsed = parse_keybind_string(t.keybind)
        if parsed is None:
            return

        keybind_id = uuid4()
        _pynput_holds[keybind_id] = parsed
        _pynput_all_binds[keybind_id] = frame, t

        def remove():
            _pynput_holds.pop(keybind_id, None)
            _pynput_all_binds.pop(keybind_id, None)
        
        return remove

    def hook_mode_down(self, frame:statemapping.NavigatorStackFrame, t:statemapping.Transition):
        parsed = parse_keybind_string(t.keybind)
        if parsed is None:
            return
        
        keybind_id = uuid4()
        _pynput_downs[keybind_id] = parsed
        _pynput_all_binds[keybind_id] = frame, t

        def remove():
            _pynput_downs.pop(keybind_id, None)
            _pynput_all_binds.pop(keybind_id, None)

        return remove

    def hook_mode_up(self, frame:statemapping.NavigatorStackFrame, t:statemapping.Transition):
        parsed = parse_keybind_string(t.keybind)
        if parsed is None:
            return
        
        keybind_id = uuid4()
        _pynput_ups[keybind_id] = parsed
        _pynput_all_binds[keybind_id] = frame, t

        def remove():
            _pynput_ups.pop(keybind_id, None)
            _pynput_all_binds.pop(keybind_id, None)
        
        return remove

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

_pynput_downs:dict[UUID, Keybind] = {}
_pynput_ups:dict[UUID, Keybind] = {}
_pynput_holds:dict[UUID, Keybind] = {}
_pynput_all_binds:dict[UUID, tuple[statemapping.NavigatorStackFrame, statemapping.Transition]] = {}

_pynput_current_keys:dict[AnyKey, datetime] = {}

_navstate_change:str = None
_navstate_change_new = threading.Event()
_navstate_change_done = threading.Event()
_navstate_change_callback:Callable[[],None] = None
_navstate_change_done.set()

def evaluate_keybind(keybind:Keybind)->bool:
    if len(_pynput_current_keys) != sum(len(o) for o in keybind):
        return False
    for order_group in keybind:
        if len(order_group) > 1:
            current = _pynput_current_keys.get(order_group[0],None)
            if current is None:
                return False
            for i in range(1,len(order_group)):
                t = _pynput_current_keys.get(order_group[i],None)
                if t is None or t < current:
                    return False
                current = t
        elif not (order_group and order_group[0] in _pynput_current_keys):
            return False
    return True

def pynput_on_press(rkey:pynput.keyboard.Key|pynput.keyboard.KeyCode|None):
    key = listener.canonical(rkey)
    if isinstance(key, (pynput.keyboard.Key,pynput.keyboard.KeyCode)):
        if key in _pynput_current_keys:
            return
        _pynput_current_keys[key] = datetime.now(timezone.utc)
    for id, keybind in list(_pynput_holds.items()):
        if not evaluate_keybind(keybind):
            continue
        frame, t = _pynput_all_binds[id]
        if nav.stack == frame:
            _navstate_change_done.wait()
            send_keypress(t.keybind, t.mode, hold_start=True)
            frame = nav.push(t.destination)
            def update():
                _pynput_holds[id] = keybind
                _pynput_all_binds[id] = nav.stack, t
            navstate_set_change(t.destination, update)
        return
    for id, keybind in list(_pynput_downs.items()):
        if not evaluate_keybind(keybind):
            continue
        frame, t = _pynput_all_binds[id]
        if nav.stack == frame:
            _navstate_change_done.wait()
            send_keypress(t.keybind, t.mode)
            navstate_set_change(t.destination)
        return

def pynput_on_release(rkey:pynput.keyboard.Key|pynput.keyboard.KeyCode|None):
    key = listener.canonical(rkey)
    if key not in _pynput_current_keys:
        return
    try:
        for id, keybind in list(_pynput_holds.items()):
            if not evaluate_keybind(keybind):
                continue
            frame, t = _pynput_all_binds[id]
            if nav.stack == frame:
                _navstate_change_done.wait()
                send_keypress(t.keybind, t.mode, hold_start=False)
                _pynput_holds.pop(id,None)
                _pynput_all_binds.pop(id,None)
                nav.pop()
                if t.pop_destination is not None:
                    navstate_set_change(t.pop_destination)
            return
        for id, keybind in list(_pynput_ups.items()):
            if not evaluate_keybind(keybind):
                continue
            frame, t = _pynput_all_binds[id]
            if nav.stack == frame:
                _navstate_change_done.wait()
                send_keypress(t.keybind, t.mode)
                navstate_set_change(t.destination)
            return
    finally:
        del _pynput_current_keys[key]

def navstate_set_change(destination:str, cb:Callable[[],None]|None=None):
    global _navstate_change, _navstate_change_callback
    _navstate_change = destination
    _navstate_change_callback = cb
    _navstate_change_new.set()

def navstate_change_handler():
    global _navstate_change, _navstate_change_callback
    try:
        while True:
            _navstate_change_new.wait()
            _navstate_change_new.clear()
            _navstate_change_done.clear()
            frame = nav.stack
            state = nav.statemap.states[_navstate_change]
            while state.change is not None and nav.stack == frame:
                name, duration = state.change
                if nav.stack is not None and nav.stack.state != state:
                    frame = nav.change(state.name)
                time.sleep(duration.total_seconds())
                state = nav.statemap.states[name]
            if nav.stack == frame and state != nav.stack.state:
                nav.change(state.name)
            _navstate_change = None
            _navstate_change_done.set()
            if _navstate_change_callback is not None:
                _navstate_change_callback()
                _navstate_change_callback = None
    except KeyboardInterrupt:
        return
    finally:
        _navstate_change_done.set()

if __name__ == "__main__":
    navstate_change_thread = threading.Thread(target=navstate_change_handler)
    navstate_change_thread.start()
    with pynput.keyboard.Listener(on_press=pynput_on_press, on_release=pynput_on_release) as listener:
        ws.run_forever()
        listener.stop()
        listener.join()