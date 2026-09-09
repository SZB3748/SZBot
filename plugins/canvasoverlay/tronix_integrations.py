from . import canvases, canvas_control as canvasctrl, canvas_math
from overlays import connections as oconnections, tronix_integrations as oti, media as omedia
from tronix import exceptions, number_units as numunits, script, script_builtins as builtins, utils
from typing import Any
from uuid import UUID


def _canvas_object_state_getter(o:script.ScriptValue[canvasctrl.CanvasObjectWrapper], n):
    objw = o.inner
    if (state := objw.obj.getstate()) is None:
        return builtins.null
    else:
        return script.ScriptValue(CanvasDrawState, canvasctrl.DrawStateWrapper(objw, state))

def _canvas_object_name_setter(o:script.ScriptValue[canvasctrl.CanvasObjectWrapper], n, v:script.ScriptVariable[str]):
    #TODO update file
    old_name = o.inner.obj.name
    new_name = v.get().inner
    o.inner.obj.name = new_name
    c = o.inner.get_canvas()
    if c is not None and (conns := c.get_live()):
        old_path = canvasctrl.canvas_data_path(canvas=c.canvas.name, object=old_name)
        new_path = canvasctrl.canvas_data_path(canvas=c.canvas.name, object=new_name)
        inst = canvasctrl.build(canvasctrl.MoveInstruction(old_path, new_path))
        for conn_id in conns:
            oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
    return script.wrap_python_value(new_name)

def _canvas_object_state_setter(o:script.ScriptValue[canvasctrl.CanvasObjectWrapper], n, v:script.ScriptVariable[str|canvasctrl.DrawStateWrapper]):
    csv = v.get()
    if csv.type.issubtype(builtins.String):
        assert isinstance(csv.inner, str)
        cs = csv.inner
    else:
        assert isinstance(csv.inner, canvasctrl.DrawStateWrapper)
        if csv.inner.is_live:
            cs = canvases.DrawState.__new__(canvases.DrawState)
            cs.__setstate__(csv.inner.state)
        else:
            cs = csv.inner.state
    o.inner.obj.current_state = cs
    c = o.inner.get_canvas()
    if c is not None and (conns := c.get_live()):
        inst = canvasctrl.build(canvasctrl.SetStateInstruction(cs, o.inner.obj))
        for conn_id in conns:
            oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)

    if o.inner.on_file:
        ... #TODO update cache and notify wrappers globally to update
    
def _canvas_object_proxy_elements_getter(o:script.ScriptValue[canvasctrl.CanvasObjectWrapper], n):
    objw = o.inner
    if (state := objw.obj.getstate()) is None:
        return builtins.null
    else:
        return script.ScriptValue(CanvasDrawElementList, canvasctrl._DrawElementList(canvasctrl.DrawStateWrapper(objw, state)))

def _canvas_object_proxy_elements_setter(o:script.ScriptValue[canvasctrl.CanvasObjectWrapper], n, v:script.ScriptVariable[canvasctrl._DrawElementList|list[canvasctrl.DrawElementWrapper]|dict[Any, canvasctrl.DrawElementWrapper]]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasObject like this while it's being used by an overlay. *point out the proper method*
    state = o.inner.obj.getstate()
    if state is None:
        ... #TODO error could not resolve CanvasObject's current drawstate
    statew = canvasctrl.DrawStateWrapper(o.inner, state)
    x = v.get()
    if x.type.issubtype(builtins.Map):
        statew.elements_proxy.replace_set(set(x.inner.values()))
    elif x.type.issubtype(builtins.List):
        statew.elements_proxy.replace_set(set(x.inner))
    else:
        statew.elements_proxy.replace(x.inner)
    return script.wrap_python_value(statew.elements_proxy)

def _canvas_object_proxy_drawspace_getter(o:script.ScriptValue[canvasctrl.CanvasObjectWrapper], n):
    objw = o.inner
    if (state := objw.obj.getstate()) is None:
        return builtins.null
    else:
        return script.ScriptValue(CanvasDrawSpace, canvasctrl.DrawSpaceWrapper(state.drawspace))

def _canvas_object_proxy_drawspace_setter(o:script.ScriptValue[canvasctrl.CanvasObjectWrapper], n, v:script.ScriptVariable[canvasctrl.DrawSpaceWrapper]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasObject like this while it's being used by an overlay. *point out the proper method*
    state = o.inner.obj.getstate()
    if state is None:
        ... #TODO error could not resolve CanvasObject's current drawstate
    statew = canvasctrl.DrawStateWrapper(o.inner, state)
    x = v.get().inner
    if x.is_live:
        dsp = canvases.DrawSpace.__new__(canvases.DrawSpace)
        dsp.__setstate__(x.drawspace.__getstate__())
        dspw = canvasctrl.DrawSpaceWrapper(statew, dsp)
    else:
        dspw = x
        dspw.parent = statew
        dsp = x.drawspace
    state.drawspace = dsp
    return script.wrap_python_value(dspw)
    
def _canvas_object_getitem(o:script.ScriptValue[canvasctrl.CanvasObjectWrapper], n:script.ScriptVariable[str]):
    obj = o.inner.obj
    state = obj.getstate()
    if state is not None:
        name = n.get().inner
        for element in state.elements:
            if element.name == name:
                return script.ScriptValue(
                    CanvasDrawElement,
                    canvasctrl.DrawElementWrapper(
                        canvasctrl.DrawStateWrapper(o.inner, state),
                        element
                    )
                )
    return builtins.null

def _canvas_object_delitem(o:script.ScriptValue[canvasctrl.CanvasObjectWrapper], n:script.ScriptVariable[str|canvasctrl.DrawElementWrapper]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasObject like this while it's being used by an overlay. *point out the proper method*
    x = n.get()
    state = o.inner.obj.getstate()
    if state is None:
        return builtins.null
    if x.type.issubtype(builtins.String):
        key = x.inner
        for element in state.elements:
            if key == element.name:
                state.elements.remove(element)
                return script.wrap_python_value(canvasctrl.DrawElementWrapper(canvasctrl.DrawStateWrapper(o.inner, state), element))
        return builtins.null
    else:
        elm = x.inner.element
    l = len(state.elements)
    state.elements.discard(elm)
    if len(state.elements) != l:
        #TODO update files if needed
        return script.wrap_python_value(canvasctrl.DrawElementWrapper(None, elm))
    else:
        return builtins.null

def _draw_state_getitem(o:script.ScriptValue[canvasctrl.DrawStateWrapper], n:script.ScriptVariable[str]):
    return script.wrap_python_value(o.inner.elements_proxy[n.get().inner])

def _draw_state_delitem(o:script.ScriptValue[canvasctrl.DrawStateWrapper], n:script.ScriptVariable[str|canvasctrl.DrawElementWrapper]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawState like this while it's being used by an overlay. *point out the proper method*
    return script.wrap_python_value(o.inner.elements_proxy.__delitem__(n.get().inner))

def _draw_state_name_setter(o:script.ScriptValue[canvasctrl.DrawStateWrapper], n, v:script.ScriptVariable[str]):
    #TODO update file
    old_name = o.inner.state.name
    new_name = v.get().inner
    o.inner.state.name = new_name
    c = o.inner.get_canvas()
    if c is not None and (conns := c.get_live()):
        old_path = canvasctrl.canvas_data_path(canvas=c.canvas.name, object=o.inner.obj.obj.name, state=old_name)
        new_path = canvasctrl.canvas_data_path(canvas=c.canvas.name, object=old_path.object, state=new_name)
        inst = canvasctrl.build(canvasctrl.MoveInstruction(old_path, new_path))
        for conn_id in conns:
            oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
    return script.wrap_python_value(o.inner.state.name)

def _draw_state_drawspace_setter(o:script.ScriptValue[canvasctrl.DrawStateWrapper], n:str, v:script.ScriptVariable[canvasctrl.DrawSpaceWrapper]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawState like this while it's being used by an overlay. *point out the proper method*
    x = v.get().inner
    if x.is_live:
        dsp = canvases.DrawSpace.__new__(canvases.DrawSpace)
        dsp.__setstate__(x.drawspace.__getstate__())
        dspw = canvasctrl.DrawSpaceWrapper(o.inner, dsp)
    else:
        dspw = x
        dspw.parent = o.inner
        dsp = x.drawspace
    o.inner.state.drawspace = dsp
    return script.wrap_python_value(dspw)

def _draw_state_elements_setter(o:script.ScriptValue[canvasctrl.DrawStateWrapper], n:str, v:script.ScriptVariable[canvasctrl._DrawElementList|list[canvasctrl.DrawElementWrapper]|dict[Any, canvasctrl.DrawElementWrapper]]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawState like this while it's being used by an overlay. *point out the proper method*
    x = v.get()
    if x.type.issubtype(builtins.Map):
        o.inner.elements_proxy.replace_set(set(x.inner.values()))
    elif x.type.issubtype(builtins.List):
        o.inner.elements_proxy.replace_set(set(x.inner))
    else:
        o.inner.elements_proxy.replace(x.inner)
    return script.wrap_python_value(o.inner.elements_proxy)

def _draw_element_name_setter(o:script.ScriptValue[canvasctrl.DrawElementWrapper], n, v:script.ScriptVariable[str]):
    #TODO update file
    old_name = o.inner.element.name
    new_name = v.get().inner
    o.inner.element.name = new_name
    c = o.inner.get_canvas()
    if c is not None and (conns := c.get_live()):
        old_path = canvasctrl.canvas_data_path(canvas=c.canvas.name, object=o.inner.state.obj.obj.name, state=o.inner.state.state.name, element=old_name)
        new_path = canvasctrl.canvas_data_path(canvas=c.canvas.name, object=old_path.object, state=old_path.state, element=new_name)
        inst = canvasctrl.build(canvasctrl.MoveInstruction(old_path, new_path))
        for conn_id in conns:
            oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
    return script.wrap_python_value(o.inner.element.name)

def _draw_element_media_setter(o:script.ScriptValue[canvasctrl.DrawElementWrapper], n, v:script.ScriptVariable[str|omedia.MediaEntry]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawElement like this while it's being used by an overlay. *point out the proper method*
    x = v.get()
    if x.type.issubtype(oti.MediaEntry):
        o.inner.element.media_name = x.inner.name
    else:
        o.inner.element.media_name = x.inner
    return script.wrap_python_value(o.inner.element.media_name)

def _draw_element_drawspace_setter(o:script.ScriptValue[canvasctrl.DrawElementWrapper], n, v:script.ScriptVariable[canvasctrl.DrawSpaceWrapper]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawElement like this while it's being used by an overlay. *point out the proper method*
    dspw = v.get().inner
    if dspw.is_live:
        dsp = canvases.DrawSpace.__new__(canvases.DrawSpace)
        dsp.__setstate__(dspw.drawspace.__getstate__())
        dspw = canvasctrl.DrawSpaceWrapper(o.inner, dsp)
    else:
        dspw.parent = o.inner
    o.inner.element.drawspace = dspw.drawspace
    return script.wrap_python_value(dspw)

def _draw_element_list_delitem(o:script.ScriptValue[canvasctrl._DrawElementList], n:script.ScriptVariable[str|canvasctrl.DrawElementWrapper]):
    return script.wrap_python_value(o.inner.__delitem__(n.get().inner))

def _canvas_object_list_delitem(o:script.ScriptValue[canvasctrl._CanvasObjectList], n:script.ScriptVariable[str|canvasctrl.CanvasObjectWrapper]):
    return script.wrap_python_value(o.inner.__delitem__(n.get().inner))

def _drawspace_xy_setter(o:script.ScriptValue[canvasctrl.DrawSpaceWrapper], n:str, v:script.ScriptVariable[int|float]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawSpace like this while it's being used by an overlay. *point out the proper method*
    x = v.get().inner
    o.inner.__dict__[n] = x
    return script.wrap_python_value(x)

def _drawspace_wh_setter(o:script.ScriptValue[canvasctrl.DrawSpaceWrapper], n:str, v:script.ScriptVariable[int|float|numunits.percent]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawSpace like this while it's being used by an overlay. *point out the proper method*
    x = v.get().inner
    if isinstance(x, numunits.percent):
        x = canvas_math.Rel(x.value, f"parent.{n}")
    o.inner.drawspace.__dict__[n[0]] = x
    return script.wrap_python_value(x)

def _drawspace_rotation_setter(o:script.ScriptValue[canvasctrl.DrawSpaceWrapper], n, v:script.ScriptVariable[int|float|numunits.percent|numunits.degrees|numunits.radians]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawSpace like this while it's being used by an overlay. *point out the proper method*
    o.inner.drawspace.r = v.get().inner
    return script.wrap_python_value(o.inner.drawspace)

def _drawspace_opacity_setter(o:script.ScriptValue[canvasctrl.DrawSpaceWrapper], n, v:script.ScriptVariable[int|float|numunits.percent]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawSpace like this while it's being used by an overlay. *point out the proper method*
    x = v.get().inner
    if isinstance(x, numunits.percent):
        o.inner.drawspace.opacity = x.value
        return script.wrap_python_value(x)
    else:
        o.inner.drawspace.opacity = x
        return script.wrap_python_value(numunits.percent(x))

def _drawspace_layer_setter(o:script.ScriptValue[canvasctrl.DrawSpaceWrapper], n, v:script.ScriptVariable[int|float]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawSpace like this while it's being used by an overlay. *point out the proper method*
    x = int(v.get().inner)
    o.inner.drawspace.opacity = x
    return script.wrap_python_value(x)

def _drawspace_parent_setter(o:script.ScriptValue[canvasctrl.DrawSpaceWrapper], n, v:script.ScriptVariable[str]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawSpace like this while it's being used by an overlay. *point out the proper method*
    x = _enum_check(v.get().inner.lower(), _PARENT_ENUM, f"{CanvasDrawSpace.name} parent value must be {", ".join(repr(x) for x in _PARENT_ENUM)}; got {{value}}")
    o.inner.drawspace.parent = x
    return script.wrap_python_value(x)

def _drawspace_content_align_setter(o:script.ScriptValue[canvasctrl.DrawSpaceWrapper], n, v:script.ScriptVariable[str]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawSpace like this while it's being used by an overlay. *point out the proper method*
    x = v.get().inner.strip().lower()
    canvases.validate_content_align(x)
    return script.wrap_python_value(x)


def _drawspace_content_overflow_setter(o:script.ScriptValue[canvasctrl.DrawSpaceWrapper], n, v:script.ScriptVariable[str]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawSpace like this while it's being used by an overlay. *point out the proper method*
    x = _enum_check(v.get().inner.lower(), _C_OVER_ENUM, f"{CanvasDrawSpace.name} content_overflow value must be {", ".join(repr(x) for x in _C_OVER_ENUM)}; got {{value}}")
    o.inner.drawspace.parent = x
    return script.wrap_python_value(x)

def _drawspace_content_underflow_setter(o:script.ScriptValue[canvasctrl.DrawSpaceWrapper], n, v:script.ScriptVariable[str]):
    if o.inner.is_live:
        ... #TODO cannot modify a CanvasDrawSpace like this while it's being used by an overlay. *point out the proper method*
    x = _enum_check(v.get().inner.lower(), _C_UNDER_ENUM, f"{CanvasDrawSpace.name} content_underflow value must be {", ".join(repr(x) for x in _C_UNDER_ENUM)}; got {{value}}")
    o.inner.drawspace.parent = x
    return script.wrap_python_value(x)

def _canvas_name_setter(o:script.ScriptValue[canvasctrl.CanvasWrapper], n, v:script.ScriptVariable[str]):
    old_name = o.inner.canvas.name
    new_name = v.get().inner
    o.inner.canvas.name = new_name
    conns = o.inner.get_live()
    if conns:
        old_path = canvasctrl.canvas_data_path(old_name)
        new_path = canvasctrl.canvas_data_path(new_name)
        inst = canvasctrl.build(canvasctrl.MoveInstruction(old_path, new_path))
        for conn_id in conns:
            oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
    return script.wrap_python_value(o.inner.canvas.name)

def _canvas_objects_setter(o:script.ScriptValue[canvasctrl.CanvasWrapper], n, v:script.ScriptVariable[dict[Any, canvasctrl.CanvasObjectWrapper]|list[canvasctrl.CanvasObjectWrapper]|canvasctrl._CanvasObjectList]):
    x = v.get()
    if x.type.issubtype(builtins.Map):
        o.inner.objects_proxy.replace_set(set(x.inner.values()))
    elif x.type.issubtype(builtins.List):
        o.inner.objects_proxy.replace_set(set(x.inner))
    else:
        o.inner.objects_proxy.replace(x.inner)
    return script.wrap_python_value(o.inner.objects_proxy)
    
def _canvas_wh_setter(o:script.ScriptValue[canvasctrl.CanvasWrapper], n:str, v:script.ScriptVariable[int|float|numunits.percent]):
    x = v.get().inner
    if isinstance(x, numunits.percent):
        x = canvas_math.Rel(x.value, f"viewport.{n}")
    o.inner.canvas.__dict__[n] = x
    conns = o.inner.get_live()
    if conns:
        inst = canvasctrl.build(canvasctrl.CanvasChangeAttributeInstruction(n, utils.serialize_value(x, type_str=True)))
        for conn_id in conns:
            oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
    return script.wrap_python_value(x)
    
def _canvas_scale_setter(o:script.ScriptValue[canvasctrl.CanvasWrapper], n, v:script.ScriptVariable[int|float|numunits.percent]):
    x = v.get().inner
    if isinstance(x, numunits.percent):
        x = x.value
    o.inner.canvas.scale = x
    conns = o.inner.get_live()
    if conns:
        inst = canvasctrl.build(canvasctrl.CanvasChangeAttributeInstruction("scale", x))
        for conn_id in conns:
            oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
    return script.wrap_python_value(x)

def _canvas_rotation_setter(o:script.ScriptValue[canvasctrl.CanvasWrapper], n, v:script.ScriptVariable[int|float|numunits.percent|numunits.degrees|numunits.radians]):
    if o.inner.is_live:
        ... #TODO notify overlays
    x = v.get().inner
    o.inner.canvas.rotation = x
    conns = o.inner.get_live()
    if conns:
        inst = canvasctrl.build(canvasctrl.CanvasChangeAttributeInstruction("rotation", utils.serialize_value(x, type_str=True)))
        for conn_id in conns:
            oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
    return script.wrap_python_value(x)

_CanvasObjectTypeAttrs = utils.ScriptAttributeHandler[canvasctrl.CanvasObjectWrapper, str]()
@_CanvasObjectTypeAttrs.enforce_child_attrs()
@_CanvasObjectTypeAttrs.attach
class _CanvasObjectType(script.ScriptDataType[canvasctrl.CanvasObjectWrapper]):
    
    f_construct = construct = utils.ScriptFunction()

    attrs = _CanvasObjectTypeAttrs
    attrs.wildcard = utils.ScriptValueAttribute[canvasctrl.CanvasObjectWrapper, str, canvasctrl.DrawElementWrapper]("").itemgetter(_canvas_object_getitem)\
        .itemdeleter(utils.TypedDeleter([builtins.String, canvasctrl.DrawElementWrapper], _canvas_object_delitem))
    attrs.entry("name", vt=str).getter(lambda o, n: script.wrap_python_value(o.inner.obj.name))\
        .setter(utils.TypedSetter(builtins.String, _canvas_object_name_setter)).nodel()
    attrs.entry("state", vt=canvasctrl.DrawStateWrapper).getter(_canvas_object_state_getter)\
        .setter(utils.TypedSetter([builtins.String, canvasctrl.DrawStateWrapper], _canvas_object_state_setter)).nodel()
    attrs.entry("statemap")

    attrs.entry("elements").getter(_canvas_object_proxy_elements_getter)\
        .setter(utils.TypedSetter([canvasctrl._DrawElementList, builtins.ListOf(canvasctrl.DrawElementWrapper), builtins.MapOf(builtins.AnyType, canvasctrl.DrawElementWrapper)], _canvas_object_proxy_elements_setter))\
        .nodel()
    attrs.entry("drawspace").getter(_canvas_object_proxy_drawspace_getter)\
        .setter(utils.TypedSetter(canvasctrl.DrawSpaceWrapper, _canvas_object_proxy_drawspace_setter)).nodel()

_CanvasDrawStateTypeAttrs = utils.ScriptAttributeHandler[canvasctrl.DrawStateWrapper, str]()
@_CanvasDrawStateTypeAttrs.enforce_child_attrs()
@_CanvasDrawStateTypeAttrs.attach
class _CanvasDrawStateType(script.ScriptDataType[canvasctrl.DrawStateWrapper]):

    f_construct = construct = utils.ScriptFunction()

    attrs = _CanvasDrawStateTypeAttrs
    attrs.wildcard = utils.ScriptValueAttribute[canvasctrl.DrawStateWrapper, str, canvasctrl.DrawElementWrapper]("")\
        .itemgetter(_draw_state_getitem).itemnoset().itemdeleter(_draw_state_delitem)
    attrs.entry("name").getter(lambda o, n: script.wrap_python_value(o.inner.state.name))\
        .setter(utils.TypedSetter(builtins.String, _draw_state_name_setter)).nodel()
    attrs.entry("drawspace").getter(lambda o, n: script.wrap_python_value(o.inner.state.drawspace))\
        .setter(utils.TypedSetter(canvasctrl.DrawSpaceWrapper, _draw_state_drawspace_setter)).nodel()
    attrs.entry("elements", vt=canvasctrl._DrawElementList).getter(lambda o, n: script.wrap_python_value(o.inner.elements_proxy))\
        .setter(utils.TypedSetter([canvasctrl._DrawElementList, builtins.ListOf(canvasctrl.DrawElementWrapper), builtins.MapOf(builtins.Any, canvasctrl.DrawElementWrapper)], _draw_state_elements_setter))\
        .nodel()


_CanvasDrawElementTypeAttrs = utils.ScriptAttributeHandler[canvasctrl.DrawElementWrapper, Any]()
@_CanvasDrawElementTypeAttrs.enforce_child_attrs()
@_CanvasDrawElementTypeAttrs.attach
class _CanvasDrawElementType(script.ScriptDataType[canvasctrl.DrawElementWrapper]):
    
    f_construct = construct = utils.ScriptFunction()

    attrs = _CanvasDrawElementTypeAttrs
    attrs.entry("name").getter(lambda o, n: script.wrap_python_value(o.inner.element.name)).setter(utils.TypedSetter(builtins.String, _draw_element_name_setter)).nodel()
    attrs.entry("media").getter(lambda o, n: script.wrap_python_value(o.inner.element.media_name))\
        .setter(utils.TypedSetter([builtins.String, oti.MediaEntry], _draw_element_media_setter)).nodel()
    attrs.entry("drawspace").getter(lambda o, n: script.wrap_python_value(canvasctrl.DrawSpaceWrapper(o.inner, o.inner.element.drawspace)))\
        .setter(utils.TypedSetter(canvasctrl.DrawSpaceWrapper, _draw_element_drawspace_setter)).nodel()

_CanvasDrawElementListTypeAttrs = utils.ScriptAttributeHandler[canvasctrl._DrawElementList, str|canvasctrl.DrawElementWrapper|canvases.DrawElement]()
@_CanvasDrawElementListTypeAttrs.enforce_child_attrs()
@_CanvasDrawElementListTypeAttrs.attach
class _CanvasDrawElementListType(script.ScriptDataType[canvasctrl._DrawElementList]):

    attrs = _CanvasDrawElementListTypeAttrs
    attrs.wildcard = utils.ScriptValueAttribute[canvasctrl._DrawElementList, str|canvasctrl.DrawElementWrapper|canvases.DrawElement]("")\
        .itemgetter(lambda o, n: script.wrap_python_value(o.inner[n.get().inner])).itemnoset()\
        .itemdeleter(_draw_element_list_delitem)
    
_CanvasObjectListTypeAttrs = utils.ScriptAttributeHandler[canvasctrl._CanvasObjectList, str|canvasctrl.CanvasObjectWrapper|canvases.CanvasObject]()
class _CanvasObjectListType(script.ScriptDataType[canvasctrl._CanvasObjectList]):

    attrs = _CanvasObjectListTypeAttrs
    #TODO add setters and deleters. must tell the overlays that the object updated and update the canvases.json file
    attrs.wildcard = utils.ScriptValueAttribute[canvasctrl._CanvasObjectList, str|canvasctrl.CanvasObjectWrapper|canvases.CanvasObject]("")\
        .itemgetter(lambda o, n: script.wrap_python_value(o.inner[n.get().inner])).itemnoset()\
        .itemdeleter(_canvas_object_list_delitem)
    

_CanvasDrawSpaceTypeAttrs = utils.ScriptAttributeHandler[canvasctrl.DrawSpaceWrapper, Any]()
class _CanvasDrawSpaceType(script.ScriptDataType[canvasctrl.DrawSpaceWrapper]):

    f_construct = construct = utils.ScriptFunction()

    attrs = _CanvasDrawSpaceTypeAttrs
    attrs.entry("x").getter(lambda o, n: script.wrap_python_value(o.inner.drawspace.x))\
        .setter(utils.TypedSetter([builtins.Integer, builtins.Float], _drawspace_xy_setter)).nodel()
    attrs.entry("y").getter(lambda o, n: script.wrap_python_value(o.inner.drawspace.y))\
        .setter(utils.TypedSetter([builtins.Integer, builtins.Float], _drawspace_xy_setter)).nodel()
    attrs.entry("width").getter(lambda o, n: script.wrap_python_value(o.inner.drawspace.w))\
        .setter(utils.TypedSetter([builtins.Integer, builtins.Float, builtins.Percent], _drawspace_wh_setter)).nodel()
    attrs.entry("height").getter(lambda o, n: script.wrap_python_value(o.inner.drawspace.h))\
        .setter(utils.TypedSetter([builtins.Integer, builtins.Float, builtins.Percent], _drawspace_wh_setter)).nodel()
    attrs.entry("rotation").getter(lambda o, n: script.wrap_python_value(o.inner.drawspace.r))\
        .setter(utils.TypedSetter([builtins.Integer, builtins.Float, builtins.Percent, builtins.Degrees, builtins.Radians], _drawspace_rotation_setter)).nodel()
    attrs.entry("opacity").getter(lambda o, n: script.wrap_python_value(numunits.percent(o.inner.drawspace.opacity)))\
        .setter(utils.TypedSetter([builtins.Integer, builtins.Float, builtins.Percent], _drawspace_opacity_setter)).nodel()
    attrs.entry("layer").getter(lambda o, n: script.wrap_python_value(o.inner.drawspace.layer))\
        .setter(utils.TypedSetter([builtins.Integer, builtins.Float], _drawspace_layer_setter)).nodel()
    attrs.entry("parent").getter(lambda o, n: script.wrap_python_value(o.inner.drawspace.parent))\
        .setter(utils.TypedSetter(builtins.String, _drawspace_parent_setter)).nodel()
    attrs.entry("content_align").getter(lambda o, n: script.wrap_python_value(o.inner.drawspace.content_align))\
        .setter(utils.TypedSetter(builtins.String, _drawspace_content_align_setter)).nodel()
    attrs.entry("content_overflow").getter(lambda o, n: script.wrap_python_value(o.inner.drawspace.content_overflow))\
        .setter(utils.TypedSetter(builtins.String, _drawspace_content_overflow_setter)).nodel()
    attrs.entry("content_underflow").getter(lambda o, n: script.wrap_python_value(o.inner.drawspace.content_underflow))\
        .setter(utils.TypedSetter(builtins.String, _drawspace_content_underflow_setter)).nodel()

_CanvasTypeAttrs = utils.ScriptAttributeHandler[canvasctrl.CanvasWrapper, str]()
class _CanvasType(script.ScriptDataType[canvasctrl.CanvasWrapper]):

    f_construct = construct = utils.ScriptFunction()

    attrs = _CanvasTypeAttrs
    attrs.entry("name").getter(lambda o, n: script.wrap_python_value(o.inner.canvas.name))\
        .setter(utils.TypedSetter(builtins.String, _canvas_name_setter)).nodel()
    attrs.entry("objects").getter(lambda o,n: script.wrap_python_value(o.inner.objects_proxy))\
        .setter(utils.TypedSetter([canvasctrl._CanvasObjectList, builtins.ListOf(canvasctrl.CanvasObjectWrapper), builtins.MapOf(builtins.AnyType, canvasctrl.CanvasObjectWrapper)], _canvas_objects_setter)).nodel()
    attrs.entry("width").getter(lambda o, n: script.wrap_python_value(o.inner.canvas.width))\
        .setter(utils.TypedSetter([builtins.Integer, builtins.Float, builtins.Percent], _canvas_wh_setter)).nodel()
    attrs.entry("height").getter(lambda o, n: script.wrap_python_value(o.inner.canvas.height))\
        .setter(utils.TypedSetter([builtins.Integer, builtins.Float, builtins.Percent], _canvas_wh_setter)).nodel()
    attrs.entry("scale").getter(lambda o, n: script.wrap_python_value(o.inner.canvas.scale))\
        .setter(utils.TypedSetter([builtins.Integer, builtins.Float, builtins.Percent], _canvas_scale_setter)).nodel()
    attrs.entry("rotation").getter(lambda o, n: script.wrap_python_value(o.inner.canvas.rotation))\
        .setter(utils.TypedSetter([builtins.Integer, builtins.Float, builtins.Percent, builtins.Degrees, builtins.Radians], _canvas_rotation_setter)).nodel()


_CanvasKeyframeTypeAttrs = utils.ScriptAttributeHandler[canvasctrl.KeyframeWrapper, Any]()
class _CanvasKeyframeType(script.ScriptDataType[canvasctrl.KeyframeWrapper]):

    attrs = _CanvasKeyframeTypeAttrs
    attrs.entry("progress").readonly(lambda o,n: script.wrap_python_value(numunits.percent(o.inner.keyframe.progress)))
    attrs.entry("target").readonly(utils.MethodGetAttribute("resolve_target"))
    attrs.entry("values").readonly(lambda o, n: script.wrap_python_value(builtins._rodict_wrapper(o.inner.values_window)))


Canvas = _CanvasType("Canvas", canvasctrl.CanvasWrapper, script.BASE_TYPE)
CanvasObject = _CanvasObjectType("CanvasObject", canvasctrl.CanvasObjectWrapper, script.BASE_TYPE)
CanvasObjectList = _CanvasObjectListType("CanvasObjectList", canvasctrl._CanvasObjectList, script.BASE_TYPE)
CanvasDrawState = _CanvasDrawStateType("CanvasDrawState", canvasctrl.DrawStateWrapper, script.BASE_TYPE)
CanvasDrawElement = _CanvasDrawElementType("CanvasDrawElement", canvasctrl.DrawElementWrapper, script.BASE_TYPE)
CanvasDrawElementList = _CanvasDrawElementListType("CanvasDrawElementList", canvasctrl._DrawElementList, script.BASE_TYPE)
CanvasDrawSpace = _CanvasDrawSpaceType("CanvasDrawSpace", canvasctrl.DrawSpaceWrapper, script.BASE_TYPE)
CanvasKeyFrame = _CanvasKeyframeType("CanvasKeyFrame", canvasctrl.KeyframeWrapper, script.BASE_TYPE)

_ScalarUnion = [builtins.Integer, builtins.Float]
_RotationUnion = [builtins.Integer, builtins.Float, builtins.Percent, builtins.Degrees, builtins.Radians]

def _enum_check(value:str, valid:set[str], message:str)->str:
    if value not in valid:
        raise exceptions.TBadValue(message.format(value=value))
    return value

_PARENT_ENUM = {"auto", "absolute", "parent"}
_C_OVER_ENUM = {"auto", "crop", "ignore", "resize", "resize force"}
_C_UNDER_ENUM = {"auto", "ignore", "resize", "resize force"}

@_CanvasType.f_construct.overload(("name", builtins.String), ("width", _ScalarUnion+[builtins.NullType, builtins.Percent], None), ("height", _ScalarUnion+[builtins.NullType, builtins.Percent], None), ("scale", [builtins.Integer, builtins.Float], 1.0), ("rotation", _RotationUnion, 0.0))
def Canvas_construct(name:script.ScriptVariable[str], width:script.ScriptVariable[int|float|numunits.percent|None], height:script.ScriptVariable[int|float|numunits.percent|None], scale:script.ScriptVariable[int|float], rotation:script.ScriptVariable[int|float|numunits.percent|numunits.degrees|numunits.radians]):
    n = name.get().inner
    #TODO validate name
    w = width.get().inner
    h = height.get().inner
    if w is None:
        w = canvas_math.Rel(1.0, "viewport.width")
    elif isinstance(w, numunits.percent):
        w = canvas_math.Rel(w.value, "viewport.width")
    if h is None:
        h = canvas_math.Rel(1.0, "viewport.height")
    elif isinstance(h, numunits.percent):
        h = canvas_math.Rel(h.value, "viewport.height")
    c = canvases.Canvas(n, w, h, scale.get().inner, rotation.get().inner)
    return script.wrap_python_value(canvasctrl.CanvasWrapper(c, False))

@_CanvasObjectType.f_construct.overload(("name", builtins.String), ("current_state", [builtins.String, CanvasDrawState]), dict(name="states", dtypes=[CanvasDrawState], pack=True), ("add_current_state_to_map", builtins.Bool, True))
def CanvasObject_construct(name:script.ScriptVariable[str], current_state:script.ScriptVariable[str|canvasctrl.DrawStateWrapper], *states:script.ScriptVariable[canvasctrl.DrawStateWrapper], add_current_state_to_map:script.ScriptVariable[bool]):
    n = name.get().inner
    #TODO validate name
    csv = current_state.get()
    statemap = {}
    if csv.type.issubtype(CanvasDrawState):
        cs = csv.inner
        assert isinstance(cs, canvasctrl.DrawStateWrapper)
        if cs.is_live:
            ns = canvases.DrawState.__new__(canvases.DrawState)
            ns.__setstate__(cs.state.__getstate__())
            cs = ns
        else:
            cs = cs.state
        if add_current_state_to_map.get().inner:
            statemap[cs.name] = cs
    else:
        cs = csv.inner
        assert isinstance(cs, str)
    for state in states:
        sw = state.get().inner
        if sw.is_live:
            s = canvases.DrawState.__new__(canvases.DrawState)
            s.__setstate__(sw.state.__getstate__())
        else:
            s = sw.state
        statemap[s.name] = s
    obj = canvases.CanvasObject(n, statemap, cs)
    return script.wrap_python_value(canvasctrl.CanvasObjectWrapper("", obj, False))

@_CanvasObjectType.f_construct.overload(("name", builtins.String), ("current_state", [builtins.String, CanvasDrawState]), ("states", builtins.ListOf(CanvasDrawState)), ("add_current_state_to_map", builtins.Bool, True))
def CanvasObject_construct_statelist(name:script.ScriptVariable[str], current_state:script.ScriptVariable[str|canvasctrl.DrawStateWrapper], states:script.ScriptVariable[list[canvasctrl.DrawStateWrapper]], add_current_state_to_map:script.ScriptVariable[bool]):
    n = name.get().inner
    #TODO validate name
    csv = current_state.get()
    statemap = {}
    if csv.type.issubtype(CanvasDrawState):
        cs = csv.inner
        assert isinstance(cs, canvasctrl.DrawStateWrapper)
        if cs.is_live:
            ns = canvases.DrawState.__new__(canvases.DrawState)
            ns.__setstate__(cs.state.__getstate__())
            cs = ns
        else:
            cs = cs.state
        if add_current_state_to_map.get().inner:
            statemap[cs.name] = cs
    else:
        cs = csv.inner
        assert isinstance(cs, str)
    for state in states.get().inner:
        if state.is_live:
            s = canvases.DrawState.__new__(canvases.DrawState)
            s.__setstate__(state.state.__getstate__())
        else:
            s = state.state
        statemap[s.name] = s
    obj = canvases.CanvasObject(n, statemap, cs)
    return script.wrap_python_value(canvasctrl.CanvasObjectWrapper("", obj, False))

@_CanvasDrawStateType.f_construct.overload(("name", builtins.String), ("drawspace", [CanvasDrawSpace, builtins.NullType], None), ("elements", [builtins.ListOf(CanvasDrawElement), builtins.NullType], None)) #TODO elements can be an elements list from another state
def CanvasDrawState_construct(name:script.ScriptVariable[str], drawspace:script.ScriptVariable[canvasctrl.DrawSpaceWrapper|None], elements:script.ScriptVariable[list[canvasctrl.DrawElementWrapper]|None]):
    n = name.get().inner
    #TODO validate name
    ds = drawspace.get().inner
    eset = set()
    statew = canvasctrl.DrawStateWrapper(None, canvases.DrawState(n, eset, None if ds is None else ds.drawspace), False)
    elmlist = elements.get()
    if elmlist.inner is not None:
        for element in elmlist.inner:
            statew.elements_proxy.add(element)
    return script.wrap_python_value(statew)

@_CanvasDrawElementType.f_construct.overload(("name", builtins.String), ("media", [builtins.String, oti.MediaEntry]), ("drawspace", [CanvasDrawSpace, builtins.NullType], None))
def CanvasDrawElement_construct(name:script.ScriptVariable[str], media:script.ScriptVariable[str|omedia.MediaEntry], drawspace:script.ScriptVariable[canvasctrl.DrawSpaceWrapper|None]):
    n = name.get().inner
    #TODO validate name
    mediav = media.get()
    if mediav.type.issubtype(builtins.String):
        media_name = mediav.inner
    else:
        assert isinstance(mediav.inner, omedia.MediaEntry)
        media_name = mediav.inner.name
    ds = drawspace.get().inner
    return script.wrap_python_value(canvasctrl.DrawElementWrapper(None, canvases.DrawElement(n, media_name, None if ds is None else ds.drawspace)))

@_CanvasDrawSpaceType.f_construct.overload(("x", _ScalarUnion, 0.0), ("y", _ScalarUnion, 0.0), ("width", _ScalarUnion+[builtins.Percent], "TODO"), ("height", _ScalarUnion+[builtins.Percent], "TODO"),
                                           ("rotation", _RotationUnion, 0.0), ("opacity", [builtins.Integer, builtins.Float, builtins.Percent], 1.0),
                                           ("layer", builtins.Integer, 0), ("parent", builtins.String, "auto"), ("content_align", builtins.String, "auto"),
                                           ("content_overflow", builtins.String, "auto"), ("content_underflow", builtins.String, "auto"))
def CanvasDrawSpace_construct(x:script.ScriptVariable[int|float], y:script.ScriptVariable[int|float],
                              width:script.ScriptVariable[int|float|numunits.percent], height:script.ScriptVariable[int|float|numunits.percent],
                              rotation:script.ScriptVariable[canvases._RotationUnion|numunits.percent], opacity:script.ScriptVariable[int|float|numunits.percent],
                              layer:script.ScriptVariable[int], parent:script.ScriptVariable[str], content_align:script.ScriptVariable[str],
                              content_overflow:script.ScriptVariable[str], content_underflow:script.ScriptVariable[str]):
    p = _enum_check(parent.get().inner.lower(), _PARENT_ENUM, f"{CanvasDrawSpace.name} parent value must be {", ".join(repr(x) for x in _PARENT_ENUM)}; got {{value}}")
    co = _enum_check(content_overflow.get().inner.lower(), _C_OVER_ENUM, f"{CanvasDrawSpace.name} content_overflow value must be {", ".join(repr(x) for x in _C_OVER_ENUM)}; got {{value}}")
    cu = _enum_check(content_underflow.get().inner.lower(), _C_UNDER_ENUM, f"{CanvasDrawSpace.name} content_underflow value must be {", ".join(repr(x) for x in _C_UNDER_ENUM)}; got {{value}}")
    xpos = x.get().inner
    ypos = y.get().inner
    w = width.get().inner
    if isinstance(w, numunits.percent):
        w = canvas_math.Rel(w.value, "parent.width")
    h = height.get().inner
    if isinstance(h, numunits.percent):
        h = canvas_math.Rel(h.value, "parent.height")
    o = opacity.get().inner
    if isinstance(o, numunits.percent):
        o = o.value
    ca = content_align.get().inner.strip().lower()
    canvases.validate_content_align(ca)
    return script.wrap_python_value(canvasctrl.DrawSpaceWrapper(canvases.DrawSpace(xpos, ypos, w, h, rotation.get().inner, o, layer.get().inner, p, ca, co, cu)))


f_get_canvas = utils.ScriptFunction()
f_keyframe_for = utils.ScriptFunction()
f_transition = utils.ScriptFunction()
f_scale = utils.ScriptFunction()
f_rotate = utils.ScriptFunction()
f_move = utils.ScriptFunction()
f_associate_canvas_with_current_overlay = utils.ScriptFunction()

@f_get_canvas.overload(("name", builtins.String))
def get_canvas(name:script.ScriptVariable[str]):
    c = canvases.merge_canvases().get(name.get().inner, None)
    if c is None:
        return builtins.null
    else:
        return script.wrap_python_value(canvasctrl.CanvasWrapper(c, True))

def _kfvgen(**kwargs):
    return {k:v for k,v in kwargs.items() if v is not None}

def _kfvc(x:script.ScriptVariable[int|float|None], y:script.ScriptVariable[int|float|None],width:script.ScriptVariable[int|float|numunits.percent|None], height:script.ScriptVariable[int|float|numunits.percent|None],rotation:script.ScriptVariable[canvases._RotationUnion|numunits.percent|None], opacity:script.ScriptVariable[int|float|numunits.percent|None],layer:script.ScriptVariable[int|None], parent:script.ScriptVariable[str|None], content_align:script.ScriptVariable[str|None],content_overflow:script.ScriptVariable[str|None], content_underflow:script.ScriptVariable[str|None]):
    p = _enum_check(parent.get().inner.lower(), _PARENT_ENUM, f"{CanvasDrawSpace.name} parent value must be {", ".join(repr(x) for x in _PARENT_ENUM)}; got {{value}}")
    co = _enum_check(content_overflow.get().inner.lower(), _C_OVER_ENUM, f"{CanvasDrawSpace.name} content_overflow value must be {", ".join(repr(x) for x in _C_OVER_ENUM)}; got {{value}}")
    cu = _enum_check(content_underflow.get().inner.lower(), _C_UNDER_ENUM, f"{CanvasDrawSpace.name} content_underflow value must be {", ".join(repr(x) for x in _C_UNDER_ENUM)}; got {{value}}")
    xpos = x.get().inner
    ypos = y.get().inner
    w = width.get().inner
    if isinstance(w, numunits.percent):
        w = canvas_math.Rel(w.value, "parent.width")
    h = height.get().inner
    if isinstance(h, numunits.percent):
        h = canvas_math.Rel(h.value, "parent.height")
    o = opacity.get().inner
    if isinstance(o, numunits.percent):
        o = o.value
    ca = content_align.get().inner.strip().lower()
    canvases.validate_content_align(ca)
    return canvases.KeyFrameValues(
        **_kfvgen(
            x=xpos, y=ypos, w=w, h=h,
            r=rotation.get().inner, opacity=o,
            layer=layer.get().inner, parent=p,
            content_align=ca, content_overflow=co,
            content_underflow=cu
        )
    )

@f_keyframe_for.overload(("target", CanvasObject), ("progress", [builtins.Integer, builtins.Float, builtins.Percent]),
                         ("x", _ScalarUnion+[builtins.NullType], None), ("y", _ScalarUnion+[builtins.NullType], None),
                         ("width", _ScalarUnion+[builtins.Percent, builtins.NullType], None),
                         ("height", _ScalarUnion+[builtins.Percent, builtins.NullType], None),
                         ("rotation", _RotationUnion+[builtins.NullType], None),
                         ("opacity", [builtins.Integer, builtins.Float, builtins.Percent, builtins.NullType], None),
                         ("layer", [builtins.Integer, builtins.NullType], None),
                         ("parent", [builtins.String, builtins.NullType], None),
                         ("content_align", [builtins.String, builtins.NullType], None),
                         ("content_overflow", [builtins.String, builtins.NullType], None),
                         ("content_underflow", [builtins.String, builtins.NullType], None))
def keyframe_for_canvas_object(target:script.ScriptVariable[canvasctrl.CanvasObjectWrapper], progress:script.ScriptVariable[int|float|numunits.percent],
                               x:script.ScriptVariable[int|float|None], y:script.ScriptVariable[int|float|None],
                               width:script.ScriptVariable[int|float|numunits.percent|None], height:script.ScriptVariable[int|float|numunits.percent|None],
                               rotation:script.ScriptVariable[canvases._RotationUnion|numunits.percent|None], opacity:script.ScriptVariable[int|float|numunits.percent|None],
                               layer:script.ScriptVariable[int|None], parent:script.ScriptVariable[str|None], content_align:script.ScriptVariable[str|None],
                               content_overflow:script.ScriptVariable[str|None], content_underflow:script.ScriptVariable[str|None]):
    progressx = progress.get().inner
    objw = target.get().inner
    if (state := objw.obj.getstate()) is None:
        ... #TODO error could not get the current state for this canvas object
    sw = canvasctrl.DrawStateWrapper(objw, state)
    kf = canvases.KeyFrame(
        float(progressx),
        None,
        _kfvc(
            x, y, width, height, rotation, opacity,
            layer, parent, content_align, content_overflow,
            content_underflow
        )
    )
    return script.wrap_python_value(canvasctrl.KeyframeWrapper(sw, kf))

@f_keyframe_for.overload(("target", CanvasDrawState), ("progress", [builtins.Integer, builtins.Float, builtins.Percent]),
                         ("x", _ScalarUnion+[builtins.NullType], None), ("y", _ScalarUnion+[builtins.NullType], None),
                         ("width", _ScalarUnion+[builtins.Percent, builtins.NullType], None),
                         ("height", _ScalarUnion+[builtins.Percent, builtins.NullType], None),
                         ("rotation", _RotationUnion+[builtins.NullType], None),
                         ("opacity", [builtins.Integer, builtins.Float, builtins.Percent, builtins.NullType], None),
                         ("layer", [builtins.Integer, builtins.NullType], None),
                         ("parent", [builtins.String, builtins.NullType], None),
                         ("content_align", [builtins.String, builtins.NullType], None),
                         ("content_overflow", [builtins.String, builtins.NullType], None),
                         ("content_underflow", [builtins.String, builtins.NullType], None))
def keyframe_for_draw_state(target:script.ScriptVariable[canvasctrl.DrawStateWrapper], progress:script.ScriptVariable[int|float|numunits.percent],
                               x:script.ScriptVariable[int|float|None], y:script.ScriptVariable[int|float|None],
                               width:script.ScriptVariable[int|float|numunits.percent|None], height:script.ScriptVariable[int|float|numunits.percent|None],
                               rotation:script.ScriptVariable[canvases._RotationUnion|numunits.percent|None], opacity:script.ScriptVariable[int|float|numunits.percent|None],
                               layer:script.ScriptVariable[int|None], parent:script.ScriptVariable[str|None], content_align:script.ScriptVariable[str|None],
                               content_overflow:script.ScriptVariable[str|None], content_underflow:script.ScriptVariable[str|None]):
    progressx = progress.get().inner
    kf = canvases.KeyFrame(
        float(progressx),
        None,
        _kfvc(
            x, y, width, height, rotation, opacity,
            layer, parent, content_align, content_overflow,
            content_underflow
        )
    )
    return script.wrap_python_value(canvasctrl.KeyframeWrapper(target.get().inner, kf))

@f_keyframe_for.overload(("target", CanvasDrawElement), ("progress", [builtins.Integer, builtins.Float, builtins.Percent]),
                         ("x", _ScalarUnion+[builtins.NullType], None), ("y", _ScalarUnion+[builtins.NullType], None),
                         ("width", _ScalarUnion+[builtins.Percent, builtins.NullType], None),
                         ("height", _ScalarUnion+[builtins.Percent, builtins.NullType], None),
                         ("rotation", _RotationUnion+[builtins.NullType], None),
                         ("opacity", [builtins.Integer, builtins.Float, builtins.Percent, builtins.NullType], None),
                         ("layer", [builtins.Integer, builtins.NullType], None),
                         ("parent", [builtins.String, builtins.NullType], None),
                         ("content_align", [builtins.String, builtins.NullType], None),
                         ("content_overflow", [builtins.String, builtins.NullType], None),
                         ("content_underflow", [builtins.String, builtins.NullType], None))
def keyframe_for_draw_element(target:script.ScriptVariable[canvasctrl.DrawElementWrapper], progress:script.ScriptVariable[int|float|numunits.percent],
                               x:script.ScriptVariable[int|float|None], y:script.ScriptVariable[int|float|None],
                               width:script.ScriptVariable[int|float|numunits.percent|None], height:script.ScriptVariable[int|float|numunits.percent|None],
                               rotation:script.ScriptVariable[canvases._RotationUnion|numunits.percent|None], opacity:script.ScriptVariable[int|float|numunits.percent|None],
                               layer:script.ScriptVariable[int|None], parent:script.ScriptVariable[str|None], content_align:script.ScriptVariable[str|None],
                               content_overflow:script.ScriptVariable[str|None], content_underflow:script.ScriptVariable[str|None]):
    progressx = progress.get().inner
    elmw = target.get().inner
    kf = canvases.KeyFrame(
        float(progressx),
        elmw.element.name,
        _kfvc(
            x, y, width, height, rotation, opacity,
            layer, parent, content_align, content_overflow,
            content_underflow
        )
    )
    return script.wrap_python_value(canvasctrl.KeyframeWrapper(elmw.state, kf))

@f_transition.overload(("object", CanvasObject), ("destination", [builtins.String, CanvasDrawState]))
def transition(object:script.ScriptVariable[canvasctrl.CanvasObjectWrapper], destination:script.ScriptVariable[str|canvasctrl.DrawStateWrapper]):
    objw = object.get().inner
    c = objw.get_canvas()
    if c is not None and (conns:=c.get_live()):
        state = objw.obj.getstate()
        if state is None:
            ... #TODO error could not resolve CanvasObject's current state to use as transition start
        t = canvases.Transition(state, [], destination.get().inner.state)
        inst = canvasctrl.build(canvasctrl.TransitionInstruction(objw.obj, t))
        for conn_id in conns:
            oconnections.default_connection_manager.send_data_to_connection(conn_id, inst)
     

@f_transition.overload(("object", CanvasObject), ("keyframes", builtins.ListOf(CanvasKeyFrame)), ("destination", CanvasDrawState))
def transition_keyframes(object:script.ScriptVariable[canvasctrl.CanvasObjectWrapper], keyframes:script.ScriptVariable[list[canvasctrl.KeyframeWrapper]], destination:script.ScriptVariable[canvasctrl.DrawStateWrapper]):
    ...

@f_associate_canvas_with_current_overlay.overload(("canvas", [builtins.String, Canvas]), pass_ctx=True)
async def associate_canvas_with_current_overlay(ctx:script.ScriptContext, canvas:script.ScriptVariable[str|canvasctrl.CanvasWrapper]):
    cpid = oti._get_layout_cprocid(ctx)
    cprocess = await oti._get_layout_cprocess(cpid)
    if isinstance(cprocess.token, UUID):
        cv = canvas.get()
        if cv.type.issubtype(builtins.String):
            cname = cv.inner
        else:
            cname = cv.inner.canvas.name
        canvasctrl.associate(cname, cprocess.token)
    else:
        ... #TODO error could not identify overlay from context. make sure you are calling this function in a layout construction action for a layout or sublayout owned by an overlay


@f_scale.overload(("object", CanvasObject), ("value", [builtins.Integer, builtins.Float, builtins.Percent]))
def scale_object(object:script.ScriptVariable[canvasctrl.CanvasObjectWrapper], value:script.ScriptVariable[int|float|numunits.percent]):
    ...

@f_scale.overload(("state", CanvasDrawState), ("value", [builtins.Integer, builtins.Float, builtins.Percent]))
def scale_state(state:script.ScriptVariable[canvasctrl.DrawStateWrapper], value:script.ScriptVariable[int|float|numunits.percent]):
    ...

@f_scale.overload(("element", CanvasDrawElement), ("value", [builtins.Integer, builtins.Float, builtins.Percent]))
def scale_element(element:script.ScriptVariable[canvasctrl.DrawElementWrapper], value:script.ScriptVariable[int|float|numunits.percent]):
    ...

@f_scale.overload(("drawspace", CanvasDrawSpace), ("value", [builtins.Integer, builtins.Float, builtins.Percent]))
def scale_drawspace(drawspace:script.ScriptVariable[canvasctrl.DrawSpaceWrapper], value:script.ScriptVariable[int|float|numunits.percent]):
    ...

