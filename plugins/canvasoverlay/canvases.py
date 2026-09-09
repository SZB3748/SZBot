from . import canvas_math as cvm
import copy
import datafile
import json
import os
import overlays
import re
import threading
import tronix
from tronix import number_units as numunits
from typing import Any, Literal, Union
from uuid import UUID

KEYFRAME_IGNORE_VALUE = object() #used by keyframes to indicate the value is not modified
CANVAS_FILE = datafile.makepath("canvases.json")


_ScalarUnion = int|float|cvm.Rel|cvm.RelPromise
_RotationUnion = int|float|cvm.Rel|cvm.RelPromise|numunits.degrees|numunits.radians|numunits.percent
_DrawSpaceParentTypes = Literal["auto","absolute","parent"]
_DrawSpaceContentOverflowTypes = Literal["auto", "crop", "ignore", "resize", "resize force"]
_DrawSpaceContentUnderflowTypes = Literal["auto", "ignore", "resize", "resize force"]

_CONTENT_ALIGN_VALIDATE_PATTERN = re.compile(r"(?P<hz>left|right)|(?P<vt>top|bottom)|(?P<neutral>middle|center)\s*")

def validate_content_align(s:str)->tuple[bool, bool]:
    s = s.strip().lower()
    if s == "auto":
        return
    start = 0
    hz = False
    vt = False
    count = 0
    while start < len(s):
        m = _CONTENT_ALIGN_VALIDATE_PATTERN.match(s, pos=start)
        if m is None:
            ... #TODO error unknown identifier
        elif m["hz"] is not None:
            if hz:
                ... #TODO error duplicate
            else:
                hz = True
        elif m["vt"] is not None:
            if vt:
                ... #TODO error duplicate
            else:
                vt = True
        elif m["neutral"] is None:
            ... #TODO error unexpected identifier
        count += 1
        start = m.endpos
    if count < 1 or count > 2:
        ... #TODO error must have 1 or 2 idenfifiers
    return hz, vt


class DrawSpace:

    INTERPOLATABLE_NAMES = "x", "y", "w", "h", "r", "opacity", "layer", "parent", "content_align", "content_overflow", "content_underflow"

    def __init__(self, x:_ScalarUnion=0.0, y:_ScalarUnion=0.0, w:_ScalarUnion=0.0, h:_ScalarUnion=0.0, r:_RotationUnion=0.0,
                 opacity:int|float=1.0, layer:int=0, parent:_DrawSpaceParentTypes="auto", content_align:str="auto",
                 content_overflow:_DrawSpaceContentOverflowTypes="auto", content_underflow:_DrawSpaceContentUnderflowTypes="auto",
                 ):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.r = r
        self.opacity = opacity
        self.layer = layer
        self.parent = parent
        self.content_align = content_align #auto= canvas: bottom left; object: bottom left; element: center
        self.content_overflow = content_overflow #auto= canvas: crop; object: ignore; element: ignore
        self.content_underflow = content_underflow #auto= canvas: ignore; object: ignore; element: resize

    def __getstate__(self):
        return dict(
            x=tronix.utils.serialize_value(self.x, type_str=True),
            y=tronix.utils.serialize_value(self.y, type_str=True),
            w=tronix.utils.serialize_value(self.w, type_str=True),
            h=tronix.utils.serialize_value(self.h, type_str=True),
            r=tronix.utils.serialize_value(self.r, type_str=True),
            opacity=self.opacity,
            layer=self.layer,
            parent=self.parent,
            content_align=self.content_align,
            content_overflow=self.content_overflow,
            content_underflow=self.content_underflow
        )
    
    def __setstate__(self, d:dict[str]):
        self.x:_ScalarUnion = tronix.utils.deserialize_value(d["x"])
        self.y:_ScalarUnion = tronix.utils.deserialize_value(d["y"])
        self.w:_ScalarUnion = tronix.utils.deserialize_value(d["w"])
        self.h:_ScalarUnion = tronix.utils.deserialize_value(d["h"])
        self.r:_RotationUnion = tronix.utils.deserialize_value(d["r"])
        self.opacity = float(d["opacity"])
        self.layer = int(d["layer"])
        self.parent = str(d.get("parent", "auto"))
        self.content_align = str(d.get("content_align", "auto"))
        self.content_overflow = str(d.get("content_overflow", "auto"))
        self.content_underflow = str(d.get("content_underflow", "auto"))

class DrawElement:
    def __init__(self, name:str, media_name:str, drawspace:DrawSpace|None=None):
        self.name = name
        self.media_name = media_name
        self.drawspace = DrawSpace(w=cvm.Rel(1.0, "object.width"), h=cvm.Rel(1.0, "object.height")) if drawspace is None else drawspace

    def __getstate__(self):
        return dict(
            name=self.name, media_name=self.media_name,
            drawspace=self.drawspace.__getstate__()
        )
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.media_name = str(d["media_name"])
        drawspace = DrawSpace.__new__(DrawSpace)
        drawspace.__setstate__(d["drawspace"])
        self.drawspace = drawspace

class DrawState:
    def __init__(self, name:str, elements:set[DrawElement]|None=None, drawspace:DrawSpace|None=None):
        self.name = name
        self.elements:set[DrawElement] = set() if elements is None else elements
        self.drawspace = DrawSpace(w=cvm.Rel(1.0, "canvas.width"), h=cvm.Rel(1.0, "canvas.height")) if drawspace is None else drawspace
    
    def __getstate__(self):
        return dict(
            name=self.name, elements=[elm.__getstate__() for elm in self.elements],
            drawspace=self.drawspace.__getstate__()
        )
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        elements:set[DrawElement] = set()
        esd = d.get("elements",None)
        if isinstance(esd, list):
            for ed in esd:
                element = DrawElement.__new__(DrawElement)
                element.__setstate__(ed)
                elements.add(element)
        self.elements = elements
        drawspace = DrawSpace.__new__(DrawSpace)
        drawspace.__setstate__(d["drawspace"])
        self.drawspace = drawspace

class CanvasObject:
    def __init__(self, name:str, statemap:dict[str, DrawState], current_state:str|DrawState):
        self.name = name
        self.statemap = statemap
        self.current_state = current_state

    @property
    def state(self):
        if isinstance(self.current_state, str):
            return self.statemap[self.current_state]
        else:
            return self.current_state
        
    def getstate(self):
        if isinstance(self.current_state, str):
            return self.statemap.get(self.current_state, None)
        else:
            return self.current_state

    def __getstate__(self):
        return dict(
            name=self.name,
            statemap={
                n:state.__getstate__() for n,state in self.statemap.items()
            },
            current_state=self.current_state if isinstance(self.current_state, str) else self.current_state.__getstate__()
        )
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        statemap = {}
        smd = d.get("statemap",None)
        if isinstance(smd, dict):
            for n, sd in smd.items():
                statemap[n] = state = DrawState.__new__(DrawState)
                state.__setstate__(sd)
        self.statemap = statemap
        sd = d["state"]
        if isinstance(sd, str):
            self.state = sd
        elif isinstance(sd, dict):
            state = DrawState.__new__(DrawState)
            state.__setstate__(sd)
            self.state = state


class Canvas:
    def __init__(self, name:str, width:_ScalarUnion, height:_ScalarUnion, scale:int|float=1.0, rotation:_RotationUnion=0.0):
        self.name = name
        self.objects:set[CanvasObject] = set()
        self.width = width
        self.height = height
        self.scale = scale
        self.rotation = rotation
    
    def __getstate__(self):
        return dict(
            name=self.name, objects=[obj.__getstate__() for obj in self.objects],
            width=tronix.utils.serialize_value(self.width, type_str=True),
            height=tronix.utils.serialize_value(self.height, type_str=True),
            scale=self.scale,
            rotation=tronix.utils.serialize_value(self.rotation)
        )
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        objects = set()
        osd = d.get("objects",None)
        if isinstance(osd, list):
            for od in osd:
                obj = CanvasObject.__new__(CanvasObject)
                obj.__setstate__(od)
                objects.add(obj)
        self.objects = objects
        self.width:_ScalarUnion = tronix.utils.deserialize_value(d["width"]).inner
        self.height:_ScalarUnion = tronix.utils.deserialize_value(d["height"]).inner
        self.scale = float(d["scale"])
        self.rotation:_RotationUnion = tronix.utils.deserialize_value(d["rotation"]).inner


class KeyFrameValues(DrawSpace):
    def __init__(self, x=KEYFRAME_IGNORE_VALUE, y=KEYFRAME_IGNORE_VALUE, w=KEYFRAME_IGNORE_VALUE, h=KEYFRAME_IGNORE_VALUE,
                 r=KEYFRAME_IGNORE_VALUE, opacity=KEYFRAME_IGNORE_VALUE, layer=KEYFRAME_IGNORE_VALUE, parent=KEYFRAME_IGNORE_VALUE,
                 content_align=KEYFRAME_IGNORE_VALUE, content_overflow=KEYFRAME_IGNORE_VALUE, content_underflow=KEYFRAME_IGNORE_VALUE):
        super().__init__(x, y, w, h, r, opacity, layer, parent, content_align, content_overflow, content_underflow)

class KeyFrame:
    def __init__(self, progress:float, target:str|None=None, values:KeyFrameValues=None):
        self.progress = progress
        self.target = target
        self.values = KeyFrameValues() if values is None else values

class InvalidTransitionException:
    "Transition is not defined correctly."

ValueTransitions = dict[str, list[tuple[float, Any]]]

def _initialize_value_transitions(ds:DrawSpace, p:float=0.0)->ValueTransitions:
    return {k:[] if (v:=getattr(ds, k, KEYFRAME_IGNORE_VALUE)) is KEYFRAME_IGNORE_VALUE else [(p, tronix.utils.serialize_value(v, type_str=True))] for k in ds.INTERPOLATABLE_NAMES}

def _add_keyframe(vt:ValueTransitions, p:float, kfv:KeyFrameValues):
    for k in kfv.INTERPOLATABLE_NAMES:
        v = getattr(kfv, k, KEYFRAME_IGNORE_VALUE)
        if v is not KEYFRAME_IGNORE_VALUE:
            l = vt.get(k, None)
            if l is None:
                l = vt[k] = []
            l.append((p, tronix.utils.serialize_value(v, type_str=True)))

class Transition:
    def __init__(self, start:DrawState, keyframes:list[KeyFrame], end:DrawState):
        self.start = start
        self.keyframes = keyframes
        self.end = end

    def calculate_transition_tables(self):
        for kf in self.keyframes:
            if kf.progress <= 0 or kf.progress > 1:
                raise InvalidTransitionException("Keyframe progess values must be between 0.0 and 1.0 (0 to 100%), not including 0.0 but including 1.0.")
        object_values:ValueTransitions = _initialize_value_transitions(self.start.drawspace)
        elements_values = {
            elm.name: _initialize_value_transitions(elm.drawspace)
            for elm in self.start.elements
        }
        kfs = sorted(self.keyframes, key=lambda kf: kf.progress)
        for kf in kfs:
            if kf.target is None:
                _add_keyframe(object_values, kf.progress, kf.values)
            elif kf.target in elements_values:
                _add_keyframe(elements_values[kf.target], kf.progress, kf.values)
            else:
                elements_values[kf.target] = _initialize_value_transitions(kf.values, kf.progress)
        return object_values, elements_values


runtime_canvases:dict[str, Canvas] = {

}

class _canvas_cache_entry:
    def __init__(self, cache:dict[str]|None=None, lock:Union[threading.Lock, None]=None):
        self.cache = {} if cache is None else cache
        self.lock = threading.Lock() if lock is None else lock
    
    def get(self):
        with self.lock:
            return copy.deepcopy(self.cache)
        
    def set(self, value, lock:bool=True): #value must be of type dict[str]
        if isinstance(value, dict):
            pop_keys = []
            for k, v in value.items():
                if not isinstance(k, str):
                    pop_keys.append(k)
            for k in pop_keys:
                del value[k]
        else:
            return False
        if lock:
            with self.lock:
                self.cache = value
        else:
            self.cache = value
        return True

_canvas_cache_mtime:float = 0.0
_canvas_cache:dict[str, _canvas_cache_entry] = {}
_canvas_cache_lock = threading.Lock()


def _update_cache():
    global _canvas_cache_mtime

    if not os.path.isfile(CANVAS_FILE):
        return
    mtime = os.stat(CANVAS_FILE).st_mtime
    if mtime == _canvas_cache_mtime:
        return
    with open(CANVAS_FILE) as f:
        c = json.load(f)
    
    if isinstance(c, dict):
        all_names = set(c.keys()) + set(_canvas_cache.keys())
        with _canvas_cache_lock:
            for name in all_names:
                if name in c:
                    if name in _canvas_cache: #update
                        _canvas_cache[name].set(c[name])
                    else: #new
                        _canvas_cache[name] = _canvas_cache_entry(c[name])
                else: #delete
                    del _canvas_cache[name]

def _save_cache():
    global _canvas_cache_mtime

    with _canvas_cache_lock:
        d = {name:entry.cache for name, entry in _canvas_cache.items()}
    c = json.dumps(d, indent=4, ensure_ascii=False)

    with open(CANVAS_FILE, "w") as f:
        f.write(c)

    _canvas_cache_mtime = os.stat(CANVAS_FILE).st_mtime

def load_canvases()->dict[str, Canvas]:
    _update_cache()
    rtv:dict[str, Canvas] = {}
    with _canvas_cache_lock:
        for name, entry in _canvas_cache.items():
            rtv[name] = c = Canvas.__new__(Canvas)
            c.__setstate__(entry.get())
    return rtv

def load_canvas(name:str)->Canvas|None:
    _update_cache()
    with _canvas_cache_lock:
        entry = _canvas_cache.get(name, None)
        if entry is None:
            return None
        c = Canvas.__new__(Canvas)
        c.__setstate__(entry.get())
        return c


def save_canvases(canvases:dict[str, Canvas], clean:bool=True):
    with _canvas_cache_lock:
        if clean:
            remove_names = set(_canvas_cache.keys()) - set(canvases.keys())
            for name in remove_names:
                del _canvas_cache[name]
        else:
            _update_cache()
        for name, c in canvases.items():
            cd = c.__getstate__()
            entry = _canvas_cache.get(name, None)
            if entry is None:
                _canvas_cache[name] = _canvas_cache_entry(cd)
            else:
                entry.set(cd)
    _save_cache()
    

def merge_canvases()->dict[str, Canvas]:
    d = runtime_canvases.copy()
    d.update(load_canvases())
    return d
