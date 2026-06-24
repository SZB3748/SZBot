from . import connections, layouts, media
import actions
import bs4
import os
from tronix import script, script_builtins as builtins, utils
import tronix_integrations as ti
from typing import Any, BinaryIO, Callable
from uuid import UUID
from werkzeug.security import safe_join

class _HTMLElement:
    @staticmethod
    def from_inner(inner:bs4.Tag):
        elm = _HTMLElement(inner.name, inner.attrs, inner.string)
        elm._inner = inner
        elm._child_list = _HTMLElementChildList(inner)
        return elm

    def __init__(self, tag:str, attrs:dict[str]|None=None, inner_text:str|None=None):
        self._tag = tag
        self._attrs = attrs
        self._inner_text = inner_text
        self._inner:bs4.Tag = None
        self._child_list:_HTMLElementChildList|None = None

    @property
    def parent(self):
        inner = self.resolve_inner(None)
        parent = inner.parent
        if parent is None:
            return None
        else:
            return _HTMLElement.from_inner(parent)
        
    @parent.setter
    def parent(self, p:"_HTMLElement|None"):
        inner = self.resolve_inner(None)
        parent = inner.parent
        if parent is not None:
            inner.unwrap()
        if p is not None:
            inner.wrap(p.resolve_inner(None))

    @property
    def tag(self):
        if self._inner is None:
            return self._tag
        else:
            return self._inner.name
    
    @tag.setter
    def tag(self, value:str):
        self._tag = value
        if self._inner is not None:
            self._inner.name = value
    
    @property
    def attrs(self):
        if self._inner is None:
            return self._attrs
        else:
            return self._inner.attrs
    
    @attrs.setter
    def attrs(self, value):
        self._attrs = value
        if self._inner is not None:
            self._inner.attrs.clear()
            self._inner.attrs.update(value)

    @property
    def inner_text(self):
        if self._inner is None:
            return self._inner_text
        else:
            return self._inner.string
    
    @inner_text.setter
    def inner_text(self, value):
        self._inner_text = value
        if self._inner is not None:
            self._inner.string = value

    @property
    def children(self):
        if self._child_list is None:
            self._child_list = _HTMLElementChildList(self.resolve_inner(None))
        return self._child_list

    def resolve_inner(self, tree:bs4.BeautifulSoup|None):
        if self._inner is None:
            if tree is None:
                self._inner = bs4.Tag(name=self._tag, attrs=self._attrs)
            else:
                self._inner = tree.new_tag(self._tag, attrs=self._attrs, string=self._inner_text)
        return self._inner
    
class _HTMLElementChildList:
    def __init__(self, elm:bs4.Tag):
        self.elm = elm

_MediaEntryTypeAttrs = utils.ScriptAttributeHandler[media.MediaEntry,str]()
@_MediaEntryTypeAttrs.enforce_child_attrs()
@_MediaEntryTypeAttrs.attach
class _MediaEntryType(script.ScriptDataType[media.MediaEntry]):

    construct = f_construct = utils.ScriptFunction()

    attrs = _MediaEntryTypeAttrs

    attrs.entry("name").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter(str, utils.SimpleSetAttribute())).nodel()
    attrs.entry("filename").readonly(utils.SimpleGetAttribute())
    attrs.entry("tags").readonly(utils.SimpleGetAttribute())
    attrs.entry("mimetype").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter(str, utils.SimpleSetAttribute())).nodel()
    attrs.entry("is_rename_pending").readonly(lambda o, n: builtins.false if o.inner.name == o.inner._old_name else builtins.true)
    attrs.entry("media_url").readonly(lambda o, n: script.wrap_python_value(f"/api/media?name={o.inner.name}"))


_LayoutTypeAttrs = utils.ScriptAttributeHandler[layouts.Layout,Any]()
@_LayoutTypeAttrs.enforce_child_attrs()
@_LayoutTypeAttrs.attach
class _LayoutType(script.ScriptDataType[layouts.Layout]):
    
    construct = f_construct = utils.ScriptFunction()

    attrs = _LayoutTypeAttrs

    attrs.entry("name").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter(str, utils.SimpleSetAttribute())).nodel()
    attrs.entry("elements").readonly(utils.SimpleGetAttribute())
    attrs.entry("parameters").readonly(utils.SimpleGetAttribute())

_LayoutElementTypeAttrs = utils.ScriptAttributeHandler[layouts.LayoutElement,Any]()
@_LayoutElementTypeAttrs.enforce_child_attrs()
@_LayoutElementTypeAttrs.attach
class _LayoutElementType(script.ScriptDataType[layouts.LayoutElement]):
    
    construct = f_construct = utils.ScriptFunction()

    attrs = _LayoutElementTypeAttrs

    attrs.entry("name").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter(str, utils.SimpleSetAttribute())).nodel()
    attrs.entry("id").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter(str, utils.SimpleSetAttribute())).nodel()
    attrs.entry("construct").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter([layouts.LayoutElementConstructTrigger, builtins.NullType], utils.SimpleSetAttribute())).nodel()


_HtmlElementChildListTypeAttrs = utils.ScriptAttributeHandler[_HTMLElementChildList,int](wildcard=utils.ScriptValueAttribute(""))
@_HtmlElementChildListTypeAttrs.enforce_child_attrs()
@_HtmlElementChildListTypeAttrs.attach_some(*utils.ATTR_ATTACH_ATTRS)
class _HtmlElementChildListType(script.ScriptDataType[_HTMLElementChildList]):
    
    attrs = _HtmlElementChildListTypeAttrs
    attrs.entry("length").readonly(lambda o, n: script.wrap_python_value(len(o.inner.elm.children)))

    def getitem(self, obj, item):
        index = builtins.resolve_index_value(obj, item)
        found = obj.inner.elm.find_all(recursive=False, limit=index+1)
        if isinstance(index, int) and len(found) <= index:
            ... #TODO error index out of range
        return script.wrap_python_value(_HTMLElement.from_inner(found[index]))
        
    def setitem(self, obj, item, value):
        index = builtins.resolve_index_value(obj, item)
        v = value.get()
        if not v.type.issubtype(HTMLElement):
            utils._DEFAULT_WRITE_WRONG_TYPE(obj, item, value)
        assert isinstance(v.inner, _HTMLElement)
        found = obj.inner.elm.find_all(recursive=False, limit=index+1)
        if len(found) <= index:
            ... #TODO error index out of range
        found[index].replace_with(v.inner.resolve_inner())
        return v

    def delitem(self, obj, item):
        index = builtins.resolve_index_value(obj, item)
        found = obj.inner.elm.find_all(recursive=False, limit=index+1)
        if len(found) <= index:
            ... #TODO error index out of range
        return script.wrap_python_value(found[index].unwrap())

_HtmlElementTypeAttrs = utils.ScriptAttributeHandler[_HTMLElement,Any]()
@_HtmlElementTypeAttrs.enforce_child_attrs()
@_HtmlElementTypeAttrs.attach
class _HtmlElementType(script.ScriptDataType[_HTMLElement]):
    
    construct = f_construct = utils.ScriptFunction()

    attrs = _HtmlElementTypeAttrs
    attrs.entry("tag").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter(builtins.String, utils.SimpleSetAttribute())).nodel()
    attrs.entry("attributes").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter(builtins.Map, utils.SimpleSetAttribute())).nodel()
    attrs.entry("inner_text").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter(builtins.String, utils.SimpleSetAttribute())).nodel()
    attrs.entry("children").getter(utils.SimpleGetAttribute()).noset().nodel()
    attrs.entry("parent").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter([_HTMLElement, builtins.NullType], utils.SimpleSetAttribute())).nodel()

    def conv_str(self, value):
        return script.wrap_python_value(str(value.inner.resolve_inner(None)))


_HtmlDocumentTypeAttrs = utils.ScriptAttributeHandler[bs4.BeautifulSoup,Any]()
@_HtmlDocumentTypeAttrs.enforce_child_attrs()
@_HtmlDocumentTypeAttrs.attach
class _HtmlDocumentType(script.ScriptDataType[bs4.BeautifulSoup]):

    attrs = _HtmlDocumentTypeAttrs
    attrs.entry("children").readonly(lambda o, n: _HTMLElementChildList(o.inner))

    def conv_str(self, value):
        return script.ScriptValue(builtins.String, value.inner.prettify())


MediaEntry = _MediaEntryType("MediaEntry", media.MediaEntry, script.BASE_TYPE)
Layout = _LayoutType("Layout", layouts.Layout, script.BASE_TYPE)
LayoutElement = _LayoutElementType("LayoutElement", layouts.LayoutElement, script.BASE_TYPE)
HTMLElementChildList = _HtmlElementChildListType("HTMLElementChildList", _HTMLElementChildList, script.BASE_TYPE)
HTMLElement = _HtmlElementType("HTMLElement", _HTMLElement, script.BASE_TYPE)
HTMLDocument = _HtmlDocumentType("HTMLDocument", bs4.BeautifulSoup, HTMLElement)

f_send_to_overlay = utils.ScriptFunction()
f_get_media = utils.ScriptFunction()
f_set_html_element_text = utils.ScriptFunction()
f_set_html_element_media = utils.ScriptFunction()
f_create_media_html_element = utils.ScriptFunction()
f_resolve_layout_element_construction = utils.ScriptFunction()
f_fail_layout_element_construction = utils.ScriptFunction()
f_add_sublayout = utils.ScriptFunction()
f_get_layout_element_html = utils.ScriptFunction()
f_construct_layout = utils.ScriptFunction()

MediaElementLoader = Callable[[bs4.Tag, media.MediaEntry], None]

_tag_to_media_element_loaders:dict[str, MediaElementLoader] = {}
_mimetype_to_media_element_loaders:dict[str, MediaElementLoader] = {}
mimetype_to_media_tag:dict[str, str] = {}


def load_media_onto_src(tag:bs4.Tag, entry:media.MediaEntry):
    if mimetype_to_media_tag.get(entry.resolve_type(), None) != tag.name:
        ... #TODO error element cannot use media of type
    tag.attrs["src"] = f"/api/media?name={entry.name}"

def load_media_onto_href(tag:bs4.Tag, entry:media.MediaEntry):
    if mimetype_to_media_tag.get(entry.resolve_type(), None) != tag.name:
        ... #TODO error element cannot use media of type
    tag.attrs["href"] = f"/api/media?name={entry.name}"

def load_media_into_inner_text(tag:bs4.Tag, entry:media.MediaEntry):
    path = entry.get_path()
    with open(path) as f:
        try:
            tag.string = f.read()
        except UnicodeDecodeError:
            ... #TODO error media must be text

def load_media_into_inner_html(tag:bs4.Tag, entry:media.MediaEntry):
    path = entry.get_path()
    with open(path) as f:
        try:
            subtree = bs4.BeautifulSoup(f)
        except UnicodeDecodeError:
            ... #TODO error media must be text
    tag.extend(subtree.children)




def add_media_element_loader_tag(tag:str, loader:MediaElementLoader):
    _tag_to_media_element_loaders[tag] = loader
    return loader

def remove_media_element_loader_tag(tag:str, loader:MediaElementLoader|None=None):
    if loader is None:
        return _tag_to_media_element_loaders.pop(tag, None)
    elif _tag_to_media_element_loaders.get(tag, None) is loader:
        del _tag_to_media_element_loaders[tag]
        return loader

def add_media_element_loader_mimetype(mime:str, loader:MediaElementLoader):
    _mimetype_to_media_element_loaders[mime] = loader
    return loader

def remove_media_element_loader_mimetype(mime:str, loader:MediaElementLoader|None=None):
    if loader is None:
        return _mimetype_to_media_element_loaders.pop(mime, None)
    elif _mimetype_to_media_element_loaders.get(mime, None) is loader:
        del _mimetype_to_media_element_loaders[mime]
        return loader

def _get_layout_cprocid(ctx:script.ScriptContext):
    cprocid = _try_layout_cprocid(ctx)
    if cprocid is None:
        ... #TODO error missing process id
    return cprocid
def _try_layout_cprocid(ctx:script.ScriptContext)->UUID|None:
    ns = ctx.stack.find_name(layouts.LAYOUT_CONSTRUCTION_PROCESS_ID_VAR_NAME)
    if ns is None:
        return None
    return ns[layouts.LAYOUT_CONSTRUCTION_PROCESS_ID_VAR_NAME].get().inner

async def _get_layout_cprocess(procid:UUID):
    process = await layouts.get_construction_process(procid)
    if process is None:
        ... #TODO error process could not be found
    return process

def _get_layout_element(process:layouts.ConstructProcess, elm_id:str):
    elm = process.tree.find(id=elm_id)
    if elm is None:
        ... #TODO error element does not exist in html document
    return elm

async def _get_html_element_with_ctx_tree(ctx:script.ScriptContext, elem:script.ScriptValue[_HTMLElement]):
    procid = _try_layout_cprocid(ctx)
    elm = None
    if procid is not None:
        process = await layouts.get_construction_process(procid)
        if process is not None:
            elm = elem.inner.resolve_inner(process.tree)
    if elm is None:
        elm = elem.inner.resolve_inner(None)
    return elm

@_MediaEntryType.f_construct.overload(("name", builtins.String), ("file_extention", builtins.String), ("tags", builtins.List, []), ("mimetype", [builtins.String, builtins.NullType], None))
def MediaEntry_construct(self, name:script.ScriptVariable[str], file_extention:script.ScriptVariable[str], tags:script.ScriptVariable[list], mimetype:script.ScriptVariable[str|None]):
    ext = os.path.basename(file_extention.get().inner)
    if "." in ext:
        ext = ext.rsplit(".", 1)[-1]
    
    t = tags.get().inner
    for tag in t:
        if not isinstance(tag, str):
            ... #TODO error tags must be strings

    entry = media.MediaEntry(name.get().inner, f"{name}.{ext}", t.copy(), mimetype.get().inner)
    return script.ScriptValue(self, entry)

@_LayoutType.f_construct.overload(("name", builtins.String), ("elements", [builtins.Map, builtins.NullType], None), ("parameters", [builtins.Map, builtins.NullType], None))
def Layout_construct(self, name:script.ScriptVariable[str], elements:script.ScriptVariable[dict|None], parameters:script.ScriptVariable[dict|None]):
    el = elements.get().inner
    if el is None:
        el = {}
    else:
        for k,v in el.items():
            if not isinstance(k, str):
                ... #TODO error must be str
            if not isinstance(v, layouts.LayoutElement):
                ... #TODO error must be layout element
        el = dict(el)
    ps = parameters.get().inner
    if ps is None:
        ps = {}
    else:
        for k,v in ps.items():
            if not isinstance(k, str):
                ... #TODO error must be str
            if not isinstance(v, actions.ActionRequestedValue):
                ... #TODO error must be action requested value
        ps = dict(ps)
    return script.ScriptValue(self, layouts.Layout(name.get().inner, el, ps))

@_HtmlElementType.f_construct.overload(("tag", builtins.String), ("inner_text", builtins.String))
def HTMLElement_construct_withtext(self, tag:script.ScriptVariable[str], inner_text:script.ScriptVariable[str]):
    return script.ScriptValue(self, _HTMLElement(tag.get().inner, inner_text=inner_text.get().inner))

@_HtmlElementType.f_construct.overload(("tag", builtins.String), ("attributes", [builtins.Map, builtins.NullType], None), ("inner_text", [builtins.String, builtins.NullType], None))
def HTMLElement_construct(self, tag:script.ScriptVariable[str], attributes:script.ScriptVariable[dict|None], inner_text:script.ScriptVariable[str|None]):
    attrs = attributes.get().inner
    if attrs is not None:
        for attr in attrs:
            if not isinstance(attr, str):
                ... #TODO error attribute names must be strings
    return script.ScriptValue(self, _HTMLElement(tag.get().inner, attrs=attrs, inner_text=inner_text.get().inner))


@f_send_to_overlay.overload(("overlay", builtins.String), dict(name="data", dtypes=[builtins.AnyType], pack=True))
def send_to_overlay(overlay:script.ScriptVariable[str], *data:script.ScriptVariable):
    connections.default_connection_manager.send_data_to_overlay(overlay.get().inner, *(d.get() for d in data))

@f_get_media.overload(("name", builtins.String))
def get_media_by_name(name:script.ScriptVariable[str]):
    entry = media.load_media_entries().get(name.get().inner, None)
    return script.wrap_python_value(entry)

@f_get_media.overload(("tags", builtins.List))
def get_media_by_tags(tags:script.ScriptVariable[list]):
    return script.wrap_python_value(media.search_media_entries(media.load_media_entries(), tags.get().inner))

@builtins._FileType.f_construct.overload(("media_entry", MediaEntry), ("mode", builtins.String))
def File_construct_media(self, media_entry:script.ScriptVariable[media.MediaEntry], mode:script.ScriptVariable[str]):
    entry = media_entry.get().inner
    p = entry.get_path()
    return script.ScriptValue(self, builtins._file_wrapper(open(p, builtins.resolve_file_mode(mode)+"b")))

@builtins.f_read.overload(("media_entry", MediaEntry))
def read_file_media(media_entry:script.ScriptVariable[media.MediaEntry]):
    entry = media_entry.get().inner
    p = entry.get_path()
    with open(p, "rb") as f:
        return builtins._read_file(f, p.rsplit(".", 1)[-1], mimetype=entry.mimetype)

@builtins.f_write.overload(("media_entry", MediaEntry), ("value", builtins.AnyType))
def write_file_media(media_entry:script.ScriptVariable[media.MediaEntry], value:script.ScriptVariable):
    entry = media_entry.get().inner
    p = entry.get_path()
    with open(p, "wb") as f:
        return builtins._write_file(f, p.rsplit(".", 1)[-1], value, mimetype=entry.mimetype)

@f_set_html_element_text.overload(("text", builtins.String), pass_ctx=True)
async def set_html_element_text_autoelm(ctx:script.ScriptContext, text:script.ScriptVariable[str]):
    procid = _get_layout_cprocid(ctx)
    process = await _get_layout_cprocess(procid)

    elm = _get_layout_element(process, process.element.id)
    elm.string = text.get().inner

@f_set_html_element_text.overload(("element", [LayoutElement, HTMLElement]), ("text", builtins.String), pass_ctx=True)
async def set_html_element_text_manualelm(ctx:script.ScriptContext, element:script.ScriptVariable[layouts.LayoutElement|_HTMLElement], text:script.ScriptVariable[str]):
    elem = element.get()
    if elem.type.issubtype(LayoutElement):
        procid = _get_layout_cprocid(ctx)
        process = await _get_layout_cprocess(procid)
        elm = _get_layout_element(process, elem.inner.id)
    else:
        elm = await _get_html_element_with_ctx_tree(ctx, elem)
    elm.string = text.get().inner

@f_set_html_element_media.overload(("element", [LayoutElement, HTMLElement]), ("media_entry", [MediaEntry, builtins.String]), pass_ctx=True)
async def set_html_element_media(ctx:script.ScriptContext, element:script.ScriptVariable[layouts.LayoutElement|_HTMLElement], media_entry:script.ScriptVariable[media.MediaEntry|str]):

    elem = element.get()
    if elem.type.issubtype(LayoutElement):
        procid = _get_layout_cprocid(ctx)
        process = await _get_layout_cprocess(procid)
        elm = _get_layout_element(process, elem.inner.id)
    else:
        elm = await _get_html_element_with_ctx_tree(ctx, elem)

    medv = media_entry.get()
    if medv.type.issubtype(MediaEntry):
        assert isinstance(medv.inner, media.MediaEntry)
        entry = medv.inner
    else:
        assert isinstance(medv.inner, str)
        entry = media.load_media_entries().get(medv.inner, None)
        if entry is None:
            ... #TODO error no media with given name

    loader = _tag_to_media_element_loaders.get(elm.name, None)
    if loader is None:
        loader = _mimetype_to_media_element_loaders.get(entry.resolve_type(), None)
        if loader is None:
            ... #TODO error cannot figure out how to load media onto element
    
    loader(elm, entry)

@f_create_media_html_element.overload(("media_entry", [MediaEntry, builtins.String]))
async def create_media_element(media_entry:script.ScriptVariable[media.MediaEntry|str]):
    medv = media_entry.get()
    if medv.type.issubtype(MediaEntry):
        assert isinstance(medv.inner, media.MediaEntry)
        entry = medv.inner
    else:
        assert isinstance(medv.inner, str)
        entry = media.load_media_entries().get(medv.inner, None)
        if entry is None:
            ... #TODO error no media with given name

    mime = entry.resolve_type()
    if mime is None:
        ... #TODO error could not resolve mimetype
    tag = mimetype_to_media_tag.get(mime, None)
    if tag is None:
        ... #TODO error could not determine HTML element tag associated with the media entry's mimetype
    return script.wrap_python_value(_HTMLElement(tag))

@f_resolve_layout_element_construction.overload(pass_ctx=True)
async def resolve_layout_element_construction(ctx:script.ScriptContext):
    procid = _get_layout_cprocid(ctx)
    process = await _get_layout_cprocess(procid)
    
    await layouts.remove_construction_process(procid)
    process.finish(True)

@f_fail_layout_element_construction.overload(pass_ctx=True)
async def layout_fail_element_construction(ctx:script.ScriptContext):
    procid = _get_layout_cprocid(ctx)
    process = await _get_layout_cprocess(procid)
    
    await layouts.remove_construction_process(procid)
    process.finish(False)

@f_add_sublayout.overload(("layout", Layout), ("args", [builtins.Map, builtins.NullType], None), pass_ctx=True)
async def add_sublayout_autoelm(ctx:script.ScriptContext, layout:script.ScriptVariable[layouts.Layout], args:script.ScriptVariable[dict|None]):
    procid = _get_layout_cprocid(ctx)
    process = await _get_layout_cprocess(procid)

    a = args.get().inner
    if a is None:
        a = {}
    else:
        for k in a:
            if not isinstance(k, str):
                ... #TODO error must all be strings

    lyt = layout.get().inner
    tree = layouts.load_layout_html(safe_join(layouts.LAYOUT_DIR, f"{lyt.name}.html"))
    elm = _get_layout_element(process, process.element.id)
    subtree = await layouts._construct(tree, layout, a)
    for child in subtree.children:
        elm.append(child)
    
@f_add_sublayout.overload(("element", [LayoutElement, HTMLElement]), ("layout", Layout), ("args", [builtins.Map, builtins.NullType], None), pass_ctx=True)
async def add_sublayout_manualelm(ctx:script.ScriptContext, element:script.ScriptVariable[layouts.LayoutElement|_HTMLElement], layout:script.ScriptVariable[layouts.Layout], args:script.ScriptVariable[dict|None]):
    a = args.get().inner
    if a is None:
        a = {}
    else:
        for k in a:
            if not isinstance(k, str):
                ... #TODO error must all be strings

    lyt = layout.get().inner
    tree = layouts.load_layout_html(safe_join(layouts.LAYOUT_DIR, f"{lyt.name}.html"))
    elem = element.get()
    if elem.type.issubtype(LayoutElement):
        procid = _get_layout_cprocid(ctx)
        process = await _get_layout_cprocess(procid)
        elm = _get_layout_element(process, elem.inner.id)
    else:
        elm = await _get_html_element_with_ctx_tree(ctx, elem)
    subtree = await layouts._construct(tree, layout, a)
    for child in subtree.children:
        elm.append(child)

@f_get_layout_element_html.overload(("element", [LayoutElement, HTMLElement]), pass_ctx=True)
async def get_layout_element_html(ctx:script.ScriptContext, element:script.ScriptVariable[layouts.LayoutElement|_HTMLElement]):
    elem = element.get()
    if elem.type.issubtype(LayoutElement):
        procid = _get_layout_cprocid(ctx)
        process = await _get_layout_cprocess(procid)
        return script.wrap_python_value(_HTMLElement.from_inner(_get_layout_element(process, elem.inner.id)))
    else:
        return elem
    
@f_construct_layout.overload(("layout", Layout), ("args", [builtins.Map, builtins.NullType], None), pass_ctx=True)
async def construct_layout(ctx:script.ScriptContext, layout:script.ScriptVariable[layouts.Layout], args:script.ScriptVariable[dict|None]):
    a = args.get().inner
    if a is None:
        a = {}
    else:
        for k in a:
            if not isinstance(k, str):
                ... #TODO error must all be strings

    lyt = layout.get().inner
    tree = layouts.load_layout_html(safe_join(layouts.LAYOUT_DIR, f"{lyt.name}.html"))
    return script.wrap_python_value(await layouts._construct(tree, layout, a))

@ti.f_save.overload(dict(name="entries", dtypes=[MediaEntry], pack=True))
def save_media_entry(*entries:script.ScriptVariable[media.MediaEntry]):
    loaded = media.load_media_entries()
    for e in entries:
        entry = e.get().inner
        loaded[entry.name] = entry
    media.save_media_entries(loaded)

@builtins.f_append.overload(("target", HTMLElementChildList), ("value", [LayoutElement, HTMLElement]), pass_ctx=True)
async def html_element_append(ctx:script.ScriptContext, target:script.ScriptVariable[_HTMLElementChildList], value:script.ScriptVariable[layouts.LayoutElement|_HTMLElement]):
    elem = value.get()
    if elem.type.issubtype(LayoutElement):
        procid = _get_layout_cprocid(ctx)
        process = await _get_layout_cprocess(procid)
        elm = _get_layout_element(process, elem.inner.id)
    else:
        elm = await _get_html_element_with_ctx_tree(ctx, elem)
    target.get().inner.elm.append(elm)

@builtins.f_find.overload(("target", HTMLElementChildList), ("value", [LayoutElement, HTMLElement]), ("start", builtins.Integer, 0), ("stop", builtins.Integer, builtins._LIST_FIND_STOP_DEFAULT), pass_ctx=True)
async def html_element_find(ctx:script.ScriptContext, target:script.ScriptVariable[_HTMLElementChildList], value:script.ScriptVariable[layouts.LayoutElement|_HTMLElement], start:script.ScriptVariable[int], stop:script.ScriptVariable[int]):
    t = target.get()
    istart = builtins.resolve_index_value(t, start)
    istop = builtins.resolve_index_value(t, stop)
    elem = value.get()
    if elem.type.issubtype(LayoutElement):
        procid = _get_layout_cprocid(ctx)
        process = await _get_layout_cprocess(procid)
        elm = _get_layout_element(process, elem.inner.id)
    else:
        elm = await _get_html_element_with_ctx_tree(ctx, elem)

    tags = t.inner.elm.find_all(recursive=False)
    try:
        index = tags.index(elm, start=istart, stop=istop)
    except ValueError:
        index = -1
    return script.ScriptValue(builtins.Integer, index)

@builtins.f_find.overload(("target", HTMLElementChildList), ("value", [LayoutElement, HTMLElement]), pass_ctx=True)
async def html_element_find(ctx:script.ScriptContext, target:script.ScriptVariable[_HTMLElementChildList], value:script.ScriptVariable[layouts.LayoutElement|_HTMLElement]):
    elem = value.get()
    if elem.type.issubtype(LayoutElement):
        procid = _get_layout_cprocid(ctx)
        process = await _get_layout_cprocess(procid)
        elm = _get_layout_element(process, elem.inner.id)
    else:
        elm = await _get_html_element_with_ctx_tree(ctx, elem)
    
    if elm in target.get().inner.elm:
        return builtins.true
    else:
        return builtins.false


def _read_html(file:BinaryIO, mimetype:str):
    doc = bs4.BeautifulSoup(file.read())
    return script.ScriptValue(HTMLDocument, doc)

def _write_html(file:BinaryIO, mimetype:str, value:script.ScriptVariable):
    v = value.get()
    if v.type.issubtype(builtins.String):
        assert isinstance(v.inner, str)
        x = v.inner
    elif v.type.issubtype(HTMLElement):
        assert isinstance(v.inner, _HTMLElement)
        doc = bs4.BeautifulSoup()
        doc.append(v.inner.resolve_inner(doc))
        x = doc.prettify()
    else:
        assert isinstance(v.inner, bs4.BeautifulSoup)
        x = v.inner.prettify()
    file.write(x)


def activate():
    utils.add_type(MediaEntry)
    utils.add_type(Layout)
    utils.add_type(LayoutElement, constructor=False)
    utils.add_type(HTMLElement)
    utils.add_type(HTMLElementChildList, constructor=False)
    utils.add_type(HTMLDocument, constructor=False)

    builtins.add_read_behavior("text/html", _read_html)
    builtins.add_write_behavior("text/html", _write_html, [HTMLDocument, HTMLElement, builtins.String])

    for mime in builtins.all_mimetypes_of("image/"):
        mimetype_to_media_tag[mime] = "img"
    for mime in builtins.all_mimetypes_of("video/"):
        mimetype_to_media_tag[mime] = "video"
    for mime in builtins.all_mimetypes_of("audio/"):
        mimetype_to_media_tag[mime] = "audio"

    for mime in builtins.all_mimetypes_of("font/"):
        mimetype_to_media_tag[mime] = "link"

    for mime in builtins.all_mimetypes_of("text/"):
        add_media_element_loader_mimetype(mime, load_media_into_inner_text)
        mimetype_to_media_tag[mime] = "p"
    add_media_element_loader_mimetype("text/html", load_media_into_inner_html)

    mimetype_to_media_tag["text/html"] = "div"
    mimetype_to_media_tag["text/css"] = "style"
    mimetype_to_media_tag["text/javascript"] = mimetype_to_media_tag["application/javascript"] = "script"

    add_media_element_loader_tag("img", load_media_onto_src)
    add_media_element_loader_tag("video", load_media_onto_src)
    add_media_element_loader_tag("audio", load_media_onto_src)
    add_media_element_loader_tag("script", load_media_into_inner_text)
    add_media_element_loader_tag("style", load_media_into_inner_text)
    add_media_element_loader_tag("link", load_media_onto_href)
    add_media_element_loader_tag("a", load_media_onto_href)


    utils.merge_function("send_to_overlay", f_send_to_overlay)
    utils.merge_function("get_media", f_get_media)
    utils.merge_function("set_html_element_text", f_set_html_element_text)
    utils.merge_function("set_html_element_media", f_set_html_element_media)
    utils.merge_function("create_media_html_element", f_create_media_html_element)
    utils.merge_function("resolve_layout_element_construction", f_resolve_layout_element_construction)
    utils.merge_function("fail_layout_element_construction", f_fail_layout_element_construction)
    utils.merge_function("add_sublayout", f_add_sublayout)
    utils.merge_function("get_layout_element_html", f_get_layout_element_html)
    utils.merge_function("construct_layout", f_construct_layout)

def deactivate():
    utils.remove_type(MediaEntry)
    utils.remove_type(Layout)
    utils.remove_type(LayoutElement)
    utils.remove_type(HTMLElement)
    utils.remove_type(HTMLElementChildList)
    utils.remove_type(HTMLDocument)

    builtins.remove_read_behavior("text/html", _read_html)
    builtins.remove_write_behavior("text/html", _write_html, [HTMLDocument, HTMLElement, builtins.String])

    mimetypes_to_remove = set()
    for mime in builtins.all_mimetypes_of("image/"):
        if mimetype_to_media_tag.get(mime,None) == "img":
            mimetypes_to_remove.add(mime)
    for mime in builtins.all_mimetypes_of("video/"):
        if mimetype_to_media_tag.get(mime,None) == "video":
            mimetypes_to_remove.add(mime)
    for mime in builtins.all_mimetypes_of("audio/"):
        if mimetype_to_media_tag.get(mime,None) == "audio":
            mimetypes_to_remove.add(mime)


    for mime in builtins.all_mimetypes_of("font/"):
        if mimetype_to_media_tag.get(mime,None) == "link":
            mimetypes_to_remove.add(mime)

    for mime in builtins.all_mimetypes_of("text/"):
        remove_media_element_loader_mimetype(mime, load_media_into_inner_text)
        mimetype_to_media_tag[mime] = "p"
    remove_media_element_loader_mimetype("text/html", load_media_into_inner_html)

    mimetype_to_media_tag["text/html"] = "div"
    mimetype_to_media_tag["text/css"] = "style"
    mimetype_to_media_tag["text/javascript"] = mimetype_to_media_tag["application/javascript"] = "script"

    remove_media_element_loader_tag("img", load_media_onto_src)
    remove_media_element_loader_tag("video", load_media_onto_src)
    remove_media_element_loader_tag("audio", load_media_onto_src)
    remove_media_element_loader_tag("script", load_media_into_inner_text)
    remove_media_element_loader_tag("style", load_media_into_inner_text)
    remove_media_element_loader_tag("link", load_media_onto_href)
    remove_media_element_loader_tag("a", load_media_onto_href)


    utils.remove_function("send_to_overlay", f_send_to_overlay)
    utils.remove_function("get_media", f_get_media)
    utils.remove_function("set_html_element_text", f_set_html_element_text)
    utils.remove_function("set_html_element_media", f_set_html_element_media)
    utils.remove_function("create_media_html_element", f_create_media_html_element)
    utils.remove_function("resolve_layout_element_construction", f_resolve_layout_element_construction)
    utils.remove_function("fail_layout_element_construction", f_fail_layout_element_construction)
    utils.remove_function("add_sublayout", f_add_sublayout)
    utils.remove_function("get_layout_element_html", f_get_layout_element_html)
    utils.remove_function("construct_layout", f_construct_layout)
