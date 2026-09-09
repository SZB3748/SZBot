from . import canvases
import json
from overlays import connections as oconnections
from typing import Self
from uuid import UUID
import weakref

class CanvasWrapper:
    __slots__ = "canvas", "objects_proxy", "is_live", "on_file"

    def __init__(self, canvas:canvases.Canvas, on_file:bool):
        self.canvas = canvas
        self.objects_proxy = _CanvasObjectList()
        self.on_file = on_file

    @property
    def is_live(self):
        return self.canvas.name in overlay_connection_associations_lookup

    def get_live(self)->weakref.WeakSet[UUID]|tuple:
        return overlay_connection_associations_lookup.get(self.canvas.name, ())

    def get_canvas(self):
        return self

class CanvasObjectWrapper:
    __slots__ = "canvas", "obj"

    def __init__(self, canvas:CanvasWrapper|None, obj:canvases.CanvasObject):
        self.canvas = canvas
        self.obj = obj

    @property
    def is_live(self):
        return False if self.canvas is None else self.canvas.is_live

    @property
    def on_file(self):
        return False if self.canvas is None else self.canvas.on_file

    def get_canvas(self):
        return self.canvas

def loose_compare_canvas_objects(objw1:CanvasObjectWrapper, objw2:CanvasObjectWrapper|None):
    return objw2 is None or objw1.obj.name == objw2.obj.name and (objw2.canvas is None or objw1.canvas.canvas.name == objw2.canvas.canvas.name)

class DrawStateWrapper:
    __slots__ = "obj", "state", "elements_proxy"

    def __init__(self, obj:CanvasObjectWrapper|None, state:canvases.DrawState):
        self.obj = obj
        self.state = state
        self.elements_proxy = _DrawElementList(self)

    @property
    def is_live(self):
        return False if self.obj is None else self.obj.is_live

    @property
    def on_file(self):
        return False if self.obj is None else self.obj.on_file

    def get_canvas(self):
        if self.obj is not None:
            return self.obj.canvas

    
class DrawElementWrapper:
    __slots__ = "state", "element"

    def __init__(self, state:DrawStateWrapper|None, element:canvases.DrawElement):
        self.state = state
        self.element = element

    @property
    def is_live(self):
        return False if self.state is None else self.state.is_live

    @property
    def on_file(self):
        return False if self.state is None else self.state.on_file

    def get_canvas(self):
        if self.state is not None:
            return self.state.get_canvas()

class _DrawElementList:
    def __init__(self, sw:DrawStateWrapper):
        self.sw = sw

    def __contains__(self, item:str|canvases.DrawElement|DrawElementWrapper):
        if isinstance(item, str):
            for element in self.sw.state.elements:
                if item == element.name:
                    return True
            return False
        elif isinstance(item, DrawElementWrapper):
            elm = item.element
        elif isinstance(item, canvases.DrawElement):
            elm = item
        else:
            ... #TODO error type
        
        return elm in self.sw.state.elements
    
    def __getitem__(self, key:str):
        for element in self.sw.state.elements:
            if key == element.name:
                return DrawElementWrapper(self.sw, element)
        raise KeyError(repr(key))
    
    def __delitem__(self, key:str|DrawElementWrapper|canvases.DrawElement):
        if isinstance(key, str):
            for element in self.sw.state.elements:
                if key == element.name:
                    self.sw.state.elements.remove(element)
                    return DrawElementWrapper(self.sw, element)
            return None
        elif isinstance(key, DrawElementWrapper):
            elm = key.element
        elif isinstance(key, canvases.DrawElement):
            elm = key
        else:
            ... #TODO error type
        l = len(self.sw.state.elements)
        self.sw.state.elements.discard(elm)
        if len(self.sw.state.elements) != l:
            c = self.sw.get_canvas()
            if c is not None and (conns := c.get_live()):
                inst = build(RemoveDrawElementInstruction(elm, self.sw.state, self.sw.obj))
                for conn_id in conns:
                    oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
            return DrawElementWrapper(None, elm)
        else:
            return None

    def add(self, item:DrawElementWrapper|canvases.DrawElement):
        if isinstance(item, DrawElementWrapper):
            if item.is_live:
                elm = canvases.DrawElement.__new__(canvases.DrawElement)
                elm.__setstate__(item.element.__getstate__())
            else:
                elm = item.element
        else:
            elm = item
        popped = self.__delitem__(elm)
        self.sw.state.elements.add(elm)
        c = self.sw.get_canvas()
        if elm is not item:
            item.state = self.sw
        if c is not None and (conns := c.get_live()):
            inst = build(AddDrawElementInstruction(elm, self.sw.state, self.sw.obj))
            for conn_id in conns:
                oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
        return popped

    def replace(self, other:"_DrawElementList"):
        sse = self.sw.state.elements
        ose = other.sw.state.elements

        c = self.sw.get_canvas()
        slive = c is not None and (conns := c.get_live())
        olive = other.sw.is_live
        insts = []
        if slive:
            outgoing_difference = sse - ose
            insts.extend(build(RemoveDrawElementInstruction(element, self.sw.state, self.sw.obj)) for element in outgoing_difference)

        incoming_difference = ose - sse

        if olive:
            ecopy = sse.intersection(ose)
        else:
            ecopy = ose.copy()
    
        if slive and olive:
            for element in incoming_difference:
                insts.append(build(AddDrawElementInstruction(element, self.sw, self.sw.obj)))
                elm = canvases.DrawElement.__new__(canvases.DrawElement)
                elm.__setstate__(element.__getstate__())
                ecopy.add(elm)
        elif slive:
            insts.extend(build(AddDrawElementInstruction(element, self.sw, self.sw.obj)) for element in incoming_difference)
        elif olive:
            for element in incoming_difference:
                elm = canvases.DrawElement.__new__(canvases.DrawElement)
                elm.__setstate__(element.__getstate__())
                ecopy.add(elm)

        self.sw.state.elements = ecopy

        if insts:
            for conn_id in conns:
                oconnections.default_connection_manager.send_data_to_connection(conn_id, *insts)


    def replace_set(self, other:set[DrawElementWrapper|canvases.DrawElement]):
        sse = self.sw.state.elements

        c = self.sw.get_canvas()
        slive = c is not None and (conns := c.get_live())
        insts = []

        incoming_difference = other - sse
        ecopy = sse.intersection(other)

        if slive:
            outgoing_difference = sse - other
            insts.extend(build(RemoveDrawElementInstruction(element, self.sw.state, self.sw.obj)) for element in outgoing_difference)
            for element in incoming_difference:
                if isinstance(element, DrawElementWrapper):
                    if element.is_live:
                        elm = canvases.DrawElement.__new__(canvases.DrawElement)
                        elm.__setstate__(element.__getstate__())
                        ecopy.add(elm)
                    else:
                        ecopy.add(element.element)
                else:
                    ecopy.add(element)
                insts.append(AddDrawElementInstruction(element, self.sw, self.sw.obj))
        else:
            for element in incoming_difference:
                if isinstance(element, DrawElementWrapper):
                    if element.is_live:
                        elm = canvases.DrawElement.__new__(canvases.DrawElement)
                        elm.__setstate__(element.__getstate__())
                        ecopy.add(elm)
                    else:
                        ecopy.add(element.element)
                else:
                    ecopy.add(element)
            
        self.sw.state.elements = ecopy

        if insts:
            for conn_id in conns:
                oconnections.default_connection_manager.send_data_to_connection(conn_id, *insts)


    
class _CanvasObjectList:
    def __init__(self, c:CanvasWrapper):
        self.c = c

    def __contains__(self, item:str|CanvasObjectWrapper|canvases.CanvasObject):
        if isinstance(item, str):
            for obj in self.c.canvas.objects:
                if item == obj.name:
                    return True
            return False
        elif isinstance(item, CanvasObjectWrapper):
            o = item.obj
        elif isinstance(item, canvases.DrawElement):
            o = item
        else:
            ... #TODO error type
        
        return o in self.c.canvas.objects
    
    def __getitem__(self, key:str):
        for obj in self.c.canvas.objects:
            if key == obj.name:
                return CanvasObjectWrapper(self.c, obj, self.c.is_live)
        raise KeyError(repr(key))
    
    def __delitem__(self, key):
        if isinstance(key, str):
            for obj in self.c.canvas.objects:
                if key == obj.name:
                    self.c.canvas.objects.remove(obj)
                    return CanvasObjectWrapper(self.c, obj, self.c.is_live)
            return None
        elif isinstance(key, CanvasObjectWrapper):
            o = key.obj
        elif isinstance(key, canvases.CanvasObject):
            o = key
        else:
            ... #TODO error type
        l = len(self.c.canvas.objects)
        self.c.canvas.objects.discard(o)
        if len(self.c.canvas.objects) != l:
            conns = self.c.get_live()
            if conns:
                inst = build(RemoveCanvasObjectInstruction(o))
                for conn_id in conns:
                    oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
            return CanvasObjectWrapper(self.c, o, self.c.is_live)
        else:
            return None

    def add(self, item:CanvasObjectWrapper|canvases.CanvasObject):
        if isinstance(item, CanvasObjectWrapper):
            if item.is_live:
                o = canvases.CanvasObject.__new__(canvases.CanvasObject)
                o.__setstate__(item.obj.__getstate__())
            else:
                o = item.obj
        else:
            o = item
        popped = self.__delitem__(o)
        self.c.canvas.objects.add(o)
        if o is not item:
            item.canvas = self.c
        conns = self.c.get_live()
        if conns:
            inst = build(AddCanvasObjectInstruction(o))
            for conn_id in conns:
                oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
        return popped

    def replace(self, other:"_CanvasObjectList"):
        sso = self.c.canvas.objects
        oso = other.c.canvas.objects

        slive = conns = self.c.get_live()
        olive = other.c.is_live
        insts = []
        if slive:
            outgoing_difference = sso - oso
            insts.extend(build(RemoveCanvasObjectInstruction(o)) for o in outgoing_difference)

        incoming_difference = oso - sso

        if olive:
            ocopy = sso.intersection(oso)
        else:
            ocopy = oso.copy()
    
        if slive and olive:
            for obj in incoming_difference:
                insts.append(build(AddCanvasObjectInstruction(obj)))
                o = canvases.CanvasObject.__new__(canvases.CanvasObject)
                o.__setstate__(obj.__getstate__())
                ocopy.add(o)
        elif slive:
            insts.append(build(AddCanvasObjectInstruction(obj)) for obj in incoming_difference)
        elif olive:
            for obj in incoming_difference:
                o = canvases.CanvasObject.__new__(canvases.CanvasObject)
                o.__setstate__(obj.__getstate__())
                ocopy.add(o)
        
        self.c.canvas.objects = ocopy
        if insts:
            for conn_id in conns:
                oconnections.default_connection_manager.send_data_to_connection(conn_id, *insts)


    def replace_set(self, other:set[CanvasObjectWrapper|canvases.CanvasObject]):
        sso = self.c.canvas.objects

        slive = conns = self.c.get_live()
        insts = []

        incoming_difference = other - sso
        ocopy = sso.intersection(other)

        if slive:
            outgoing_difference = sso - other
            insts.extend(build(RemoveCanvasObjectInstruction(o)) for o in outgoing_difference)
            for obj in incoming_difference:
                if isinstance(obj, CanvasObjectWrapper):
                    if obj.is_live:
                        o = canvases.CanvasObject.__new__(canvases.CanvasObject)
                        o.__setstate__(obj.__getstate__())
                        ocopy.add(o)
                    else:
                        ocopy.add(obj.obj)
                else:
                    ocopy.add(obj)
                insts.append(build(AddCanvasObjectInstruction(obj)))
        else:
            for obj in incoming_difference:
                if isinstance(obj, CanvasObjectWrapper):
                    if obj.is_live:
                        o = canvases.CanvasObject.__new__(canvases.CanvasObject)
                        o.__setstate__(obj.__getstate__())
                        ocopy.add(o)
                    else:
                        ocopy.add(obj.obj)
                else:
                    ocopy.add(obj)
        
        self.c.canvas.objects = ocopy

        if insts:
            for conn_id in conns:
                oconnections.default_connection_manager.send_data_to_connection(conn_id, *insts)
            
class DrawSpaceWrapper:
    __slots__ = "parent", "drawspace"

    def __init__(self, parent:DrawStateWrapper|DrawElementWrapper|None, drawspace:canvases.DrawSpace):
        self.parent = parent
        self.drawspace = drawspace

    @property
    def is_live(self):
        return False if self.parent is None else self.parent.is_live

    @property
    def on_file(self):
        return False if self.parent is None else self.parent.on_file

    def get_canvas(self):
        if self.parent is not None:
            return self.parent.get_canvas()

class KeyframeWrapper:
    __slots__ = "state", "keyframe", "values_window"

    def __init__(self, state:DrawStateWrapper|None, keyframe:canvases.KeyFrame):
        self.state = state
        self.keyframe = keyframe
        self.values_window = {k:v for k,v in keyframe.values.__dict__.items() if v is not canvases.KEYFRAME_IGNORE_VALUE}

    def resolve_target(self):
        if self.state is None:
            return self.keyframe.target
        elif self.keyframe.target is None:
            return self.state
        else:
            return self.state.elements_proxy[self.keyframe.target]

class _CanvasAssociation:
    def __init__(self, name:str):
        self.name = name

    def __hash__(self):
        return hash(self.name)
    
    def __eq__(self, value):
        return self.name == value

overlay_connection_associations:weakref.WeakKeyDictionary[UUID, set[_CanvasAssociation]] = weakref.WeakKeyDictionary()
overlay_connection_associations_lookup:weakref.WeakKeyDictionary[_CanvasAssociation, weakref.WeakSet[UUID]] = weakref.WeakKeyDictionary()

def associate(canvas_name:str, connection_id:UUID):
    a = _CanvasAssociation(canvas_name)
    aset = overlay_connection_associations.get(connection_id, None)
    idset = overlay_connection_associations_lookup.get(a, None)
    if aset is None:
        overlay_connection_associations[connection_id] = {a}
    else:
        aset.add(a)
    if idset is None:
        overlay_connection_associations_lookup[a] = weakref.WeakSet({connection_id})
    else:
        idset.add(connection_id)

class canvas_data_path:

    @classmethod
    def generate(cls, value:CanvasWrapper|CanvasObjectWrapper|DrawStateWrapper|DrawElementWrapper|DrawSpaceWrapper):
        if isinstance(value, CanvasWrapper):
            return cls(canvas=value.canvas.name)
        elif isinstance(value, CanvasObjectWrapper):
            c = value.canvas
            return cls(
                canvas=None if c is None else c.canvas.name,
                object=value.obj.name
            )
        elif isinstance(value, DrawStateWrapper):
            objw = value.obj
            if objw is None:
                oname = None
                cname = None
            elif objw.canvas is None:
                oname = objw.obj.name
                cname = None
            else:
                oname = objw.obj.name
                cname = objw.canvas.canvas.name
            return cls(canvas=cname, object=oname, state=value.state.name)
        elif isinstance(value, DrawElementWrapper):
            statew = value.state
            if statew is None:
                sname = None
                oname = None
                cname = None
            else:
                objw = statew.obj
                sname = statew.state.name
                if objw is None:
                    oname = None
                    cname = None
                elif objw.canvas is None:
                    oname = objw.obj.name
                    cname = None
                else:
                    oname = objw.obj.name
                    cname = objw.canvas.canvas.name
            return cls(canvas=cname, object=oname, state=sname)
        elif isinstance(value, DrawSpaceWrapper):
            if value.parent is None:
                return cls(drawspace=True)
            else:
                cdp:Self = cls.generate(value.parent)
                cdp.drawspace = True
                return cdp
        raise TypeError(f"expected Wrapper object of a canvas data resource, got {type(value).__name__}")


    def __init__(self, canvas:str|None=None, object:str|None=None, state:str|None=None, element:str|None=None, drawspace:bool=False):
        self.canvas = canvas
        self.object = object
        self.state = state
        self.element = element
        self.drawspace = drawspace

    def __getstate__(self):
        return self.__dict__.copy()

    def __setstate__(self, d:dict[str]):
        self.__dict__.update(d)

    def copy(self):
        new = canvas_data_path.__new__(canvas_data_path)
        new.__dict__.update(self.__dict__)
        return new

class Instruction:
    NAME = None

    def __getstate__(self)->dict[str]:
        return {}

class _DrawElementInstruction(Instruction):

    def __init__(self, element:canvases.DrawElement, state:canvases.DrawState, object:canvases.CanvasObject):
        self.element = element
        self.state = state
        self.object = object

    def __getstate__(self):
        return dict(
            element=self.element.__getstate__(),
            state=self.state.__getstate__(),
            object=self.object.__getstate__()
        )

class _CanvasObjectInstruction(Instruction):

    def __init__(self, object:canvases.CanvasObject):
        self.object = object

    def __getstate__(self):
        return dict(
            object=self.object.__getstate__()
        )
    

class RemoveDrawElementInstruction(_DrawElementInstruction):
    NAME = "remove_draw_element"

class AddDrawElementInstruction(_DrawElementInstruction):
    NAME = "add_draw_element"

class RemoveCanvasObjectInstruction(_CanvasObjectInstruction):
    NAME = "remove_canvas_object"

class AddCanvasObjectInstruction(_CanvasObjectInstruction):
    NAME = "add_canvas_object"

class MoveInstruction(Instruction):

    NAME = "move"

    def __init__(self, old_path:canvas_data_path, new_path:canvas_data_path):
        self.old_path = old_path
        self.new_path = new_path

    def __getstate__(self):
        return dict(
            old_path=self.old_path.__getstate__(),
            new_path=self.new_path.__getstate__()
        )

class SetStateInstruction(Instruction):

    NAME = "set_state"

    def __init__(self, state:str|canvases.DrawState, object:canvases.CanvasObject):
        self.state = state
        self.object = object

    def __getstate__(self):
        return dict(
            state=self.state if isinstance(self.state, str) else self.state.__getstate__(),
            object=self.object.__getstate__()
        )

class CanvasChangeAttributeInstruction(Instruction):

    NAME = "canvas_change_attr"

    def __init__(self, attr_name:str, value):
        self.attr_name = attr_name
        self.value = value

    def __getstate__(self):
        return dict(
            attr_name=self.attr_name,
            value=self.value
        )

class TransitionInstruction(Instruction):

    NAME = "transition"

    def __init__(self, object:canvases.CanvasObject, transition:canvases.Transition):
        self.object = object
        self.transition = transition

    def __getstate__(self):
        otable, etables = self.transition.calculate_transition_tables()
        return dict(
            object=self.object,
            start_state=self.transition.start.__getstate__(),
            end_state=self.transition.end.__getstate__(),
            object_table=otable,
            element_tables=etables
        )


def build(inst:Instruction):
    return json.dumps(dict(
        name=inst.NAME,
        data=inst.__getstate__()
    ), ensure_ascii=False)