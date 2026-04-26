import enum
import re

KEYBIND_PATTERN = re.compile(r"[ ]*((?:(?:[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*|\([ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*\)[ ]*)|(?:\([ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*(?:\+[ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*)\)[ ]*))(?:\+[ ]*(?:(?:[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*|\([ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*\)[ ]*)|(?:\([ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*(?:\+[ ]*[',\-./0-9;=A-Z\[\\\]`a-z][ ',\-./0-9;=A-Z\[\\\]`a-z]*)\)[ ]*)))*)(?:\+[ ]*)*")
KEYBIND_SPLIT_PATTERN = re.compile(r"\+(?![^()]*\))")

class KeyBindMode(enum.Enum):
    TRIGGER_DOWN = 1
    TRIGGER_UP = 2

KeyNames = list[list[str|None]]

def parse_keybind_string(s:str, cache:bool=True)->KeyNames|None:
    if cache and s in _cached:
        return [x.copy() for x in _cached[s]]
    
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
    
    rtv = [[name if isinstance(name, str) else None for name in (name.strip() for name in group.strip(" ()").split("+"))] for group in KEYBIND_SPLIT_PATTERN.split(g1)]
    if cache:
        _cached[s] = [x.copy() for x in rtv]
    return rtv

_cached:dict[str, KeyNames] = {}

class KeyBind:
    def __init__(self, keys:str, mode:KeyBindMode):
        self.keys = keys
        self.mode = mode