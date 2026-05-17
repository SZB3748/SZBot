from . import layouts
import bs4
from tronix import script, script_builtins as builtins, utils
from uuid import UUID
from werkzeug.security import safe_join

class _HTMLElement:
    @staticmethod
    def from_inner(inner:bs4.Tag):
        elm = _HTMLElement(inner.name, inner.attrs, inner.string)
        elm._inner = inner
        return elm

    def __init__(self, tag:str, attrs:dict[str]|None=None, inner_text:str|None=None):
        self.tag = tag
        self.attrs = attrs
        self.inner_text = inner_text
        self._inner:bs4.Tag = None

    def resolve_inner(self, tree:bs4.BeautifulSoup):
        if self._inner is None:
            self._inner = tree.new_tag(self.tag, attrs=self.attrs, string=self.inner_text)
        return self._inner

class _LayoutType(script.ScriptDataType[layouts.Layout]):
    ...

class _LayoutElementType(script.ScriptDataType[layouts.LayoutElement]):
    ...

class _HtmlElementType(script.ScriptDataType[_HTMLElement]):
    
    construct = f_construct = utils.ScriptFunction()

    def getattr(self, obj, name):
        ...
    
    def setattr(self, obj, name, value):
        ...
    
    def delattr(self, obj, name):
        ...


Layout = _LayoutType("Layout", layouts.Layout, script.BASE_TYPE)
LayoutElement = _LayoutElementType("LayoutElement", layouts.Layout, script.BASE_TYPE)
HTMLElement = _HtmlElementType("HTMLElement", _HTMLElement, script.BASE_TYPE)

f_layout_set_element_text = utils.ScriptFunction()
f_layout_resolve_element_construction = utils.ScriptFunction()
f_layout_fail_element_construction = utils.ScriptFunction()
f_layout_add_sublayout = utils.ScriptFunction()
f_layout_get_element_html = utils.ScriptFunction()

def _get_layout_cprocid(ctx:script.ScriptContext)->UUID:
    ns = ctx.stack.find_name(layouts.LAYOUT_CONSTRUCTION_PROCESS_ID_VAR_NAME)
    if ns is None:
        ... #TODO error missing process id
    return ns[layouts.LAYOUT_CONSTRUCTION_PROCESS_ID_VAR_NAME].get().inner

async def _get_layout_cprocess(procid:UUID):
    process = await layouts.get_construction_process(procid)
    if process is None:
        ... #TODO error process could not be found
    return process

def _get_layout_element(process:layouts.ConstructProcess, elm_id:str):
    elm = process.tree.find(id=elm_id)
    if elm is None:
        ... #TODO element does not exist in html document
    return elm

@_HtmlElementType.f_construct.overload(("tag", builtins.String), ("inner_text", builtins.String))
def HTMLElement_construct_withtext(self, tag:script.ScriptVariable[str], inner_text:script.ScriptVariable[str]):
    return script.ScriptValue(self, _HTMLElement(tag, inner_text=inner_text))

@_HtmlElementType.f_construct.overload(("tag", builtins.String), ("attributes", [builtins.Map, builtins.NullType], None), ("inner_text", [builtins.String, builtins.NullType], None))
def HTMLElement_construct(self, tag:script.ScriptVariable[str], attributes:script.ScriptVariable[dict|None], inner_text:script.ScriptVariable[str|None]):
    attrs = attributes.get().inner
    if attrs is not None:
        for attr in attrs:
            if not isinstance(attr, str):
                ... #TODO error attribute names must be strings
    return script.ScriptValue(self, _HTMLElement(tag, attrs=attrs, inner_text=inner_text.get().inner))




@f_layout_set_element_text.overload(("text", builtins.String), pass_ctx=True)
async def layout_set_element_text_autoelm(ctx:script.ScriptContext, text:script.ScriptVariable[str]):
    procid = _get_layout_cprocid(ctx)
    process = await _get_layout_cprocess(procid)

    elm = _get_layout_element(process, process.element.id)
    elm.string = text.get().inner

@f_layout_set_element_text.overload(("element", [LayoutElement, HTMLElement]), ("text", builtins.String), pass_ctx=True)
async def layout_set_element_text_manualelm(ctx:script.ScriptContext, element:script.ScriptVariable[layouts.LayoutElement|_HTMLElement], text:script.ScriptVariable[str]):
    procid = _get_layout_cprocid(ctx)
    process = await _get_layout_cprocess(procid)

    elem = element.get()
    if elem.type.issubtype(LayoutElement):
        elm = _get_layout_element(process, elem.inner.id)
    else:
        elm = elem.inner.resolve_inner(process.tree)
    elm.string = text.get().inner

@f_layout_resolve_element_construction.overload(pass_ctx=True)
async def layout_resolve_element_construction(ctx:script.ScriptContext):
    procid = _get_layout_cprocid(ctx)
    process = await _get_layout_cprocess(procid)
    
    await layouts.remove_construction_process(procid)
    process.finish(True)

@f_layout_fail_element_construction.overload(pass_ctx=True)
async def layout_fail_element_construction(ctx:script.ScriptContext):
    procid = _get_layout_cprocid(ctx)
    process = await _get_layout_cprocess(procid)
    
    await layouts.remove_construction_process(procid)
    process.finish(False)

@f_layout_add_sublayout.overload(("layout", Layout), ("args", [builtins.Map, builtins.NullType], None), pass_ctx=True)
async def layout_add_sublayout_autoelm(ctx:script.ScriptContext, layout:script.ScriptVariable[layouts.Layout], args:script.ScriptVariable[dict|None]):
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
    
@f_layout_add_sublayout.overload(("element", [LayoutElement, HTMLElement]), ("layout", Layout), ("args", [builtins.Map, builtins.NullType], None), pass_ctx=True)
async def layout_add_sublayout_manualelm(ctx:script.ScriptContext, element:script.ScriptVariable[layouts.LayoutElement|_HTMLElement], layout:script.ScriptVariable[layouts.Layout], args:script.ScriptVariable[dict|None]):
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
    elem = element.get()
    if elem.type.issubtype(LayoutElement):
        elm = _get_layout_element(process, elem.inner.id)
    else:
        elm = elem.inner.resolve_inner(process.tree)
    subtree = await layouts._construct(tree, layout, a)
    for child in subtree.children:
        elm.append(child)

@f_layout_get_element_html.overload(("element", [LayoutElement, HTMLElement]), pass_ctx=True)
async def layout_get_element_html(ctx:script.ScriptContext, element:script.ScriptVariable[layouts.LayoutElement|_HTMLElement]):
    procid = _get_layout_cprocid(ctx)
    process = await _get_layout_cprocess(procid)

    elem = element.get()
    if elem.type.issubtype(LayoutElement):
        return script.wrap_python_value(_HTMLElement.from_inner(_get_layout_element(process, elem.inner.id)))
    else:
        return elem
    

def activate():
    utils.add_type(Layout, constructor=False)
    utils.add_type(LayoutElement, constructor=False)

    script.SCRIPT_FUNCTION_TABLE["layout_set_element_text"] = f_layout_set_element_text
    script.SCRIPT_FUNCTION_TABLE["layout_resolve_element_construction"] = f_layout_resolve_element_construction
    script.SCRIPT_FUNCTION_TABLE["layout_fail_element_construction"] = f_layout_fail_element_construction
    script.SCRIPT_FUNCTION_TABLE["layout_add_sublayout"] = f_layout_add_sublayout
