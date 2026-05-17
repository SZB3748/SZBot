import actions
import asyncio
import bs4
import datafile
import inspect
import json
import os
from tronix import script
from uuid import UUID, uuid4

LAYOUT_CONSTRUCTION_PROCESS_ID_VAR_NAME = "__layout_construction_process_id"

LAYOUT_DIR = datafile.makepath("layouts")

class LayoutElement:
    def __init__(self, name:str, id:str, construct:"LayoutElementConstructTrigger|None"):
        self.name = name
        self.id = id
        self.construct = construct

    def __getstate__(self):
        return {
            "name": self.name,
            "id": self.id,
            "construct": None if construct is None else self.construct.__getstate__()
        }
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.id = str(d["id"])
        cd = d["construct"]
        if cd is None:
            self.construct = None
        else:
            construct = ActionLayoutElementConstructTrigger.__new__(ActionLayoutElementConstructTrigger)
            construct.__setstate__(cd)
            self.construct = construct

class Layout:
    def __init__(self, name:str, elements:dict[str,LayoutElement]|None=None, parameters:dict[str, actions.ActionRequestedValue]|None=None):
        self.name = name
        self.elements = {} if elements is None else elements
        self.parameters = {} if parameters is None else parameters

    def __getstate__(self):
        return {
            "name": self.name,
            "elements": {e.name:e.__getstate__() for e in self.elements.values()},
            "parameters": {p.name:p.__getstate__() for p in self.parameters.values()},
        }
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.elements = {}
        self.parameters = {}

        elements = d["elements"]
        if isinstance(elements, dict):
            for elmd in elements.values():
                element = LayoutElement.__new__(LayoutElement)
                element.__setstate__(elmd)
                self.elements[element.name] = element

        parameters = d["parameters"]
        if isinstance(parameters, dict):
            for pd in parameters.values():
                parameter = actions.ActionRequestedValue.__new__(actions.ActionRequestedValue)
                parameter.__setstate__(pd)
                self.parameters[parameter.name] = parameter

class LayoutElementConstructContext:
    def __init__(self, layout:Layout, element:LayoutElement, layout_args:dict[str], layout_process_id:UUID):
        self.layout = layout
        self.element = element
        self.layout_args = layout_args
        self.layout_process_id = layout_process_id

class LayoutElementConstructActionValueMapping(actions.ActionValueMapping):
    def __init__(self, layout_name:str, element_name:str, parameter_names:dict[str, str], extra_data:dict[str]):
        self.layout_name = layout_name
        self.element_name = element_name
        self.parameter_names = parameter_names
        self.extra_data = extra_data

    def fill_values(self, construct_ctx:LayoutElementConstructContext):
        d = self.extra_data.copy()
        for name, arg in construct_ctx.layout_args.items():
            name = self.parameter_names.get(name, None)
            if name is not None:
                d.setdefault(name, arg)
        if self.layout_name:
            d.setdefault(self.layout_name, construct_ctx.layout)
        if self.element_name:
            d.setdefault(self.element_name, construct_ctx.element)
        return d
    
    def __getstate__(self):
        return {
            "layout_name": self.layout_name,
            "element_name": self.element_name,
            "parameter_names": self.parameter_names,
            "extra_data": actions.extra_data_serialize(self.extra_data)
        }
    
    def __setstate__(self, d:dict[str]):
        self.layout_name = str(d["layout_name"])
        self.element_name = str(d["element_name"])
        self.parameter_names:dict[str,str] = d["parameter_names"]
        self.extra_data:dict[str] = actions.extra_data_deserialize(d["extra_data"])

class LayoutElementConstructTrigger(actions.Trigger):
    def handle(self, construct_ctx:LayoutElementConstructContext):
        raise NotImplementedError
    
class ActionLayoutElementConstructTrigger(LayoutElementConstructTrigger):
    def __init__(self, action_name:str, action_mapping:LayoutElementConstructActionValueMapping):
        self.action_name = action_name
        self.action_mapping = action_mapping
    
    def __getstate__(self):
        return {
            "action_name": self.action_name,
            "action_mapping": self.action_mapping.__getstate__()
        }
    
    def __setstate__(self, d:dict[str]):
        self.action_name = str(d["action_name"])
        action_mapping = LayoutElementConstructActionValueMapping.__new__(LayoutElementConstructActionValueMapping)
        action_mapping.__setstate__(d["action_mapping"])
        self.action_mapping = action_mapping

    def handle(self, construct_ctx):
        action = actions.load_action_table().get(self.action_name, None)
        if action is None:
            ... #TODO exception action not found

        filled = self.action_mapping.fill_values(construct_ctx)
        script_scope = action.collect_script_values(filled)
        s = script.Script(action.script, script_scope)

        if action.script_environment is None or actions.match_environment_name(action.script_environment, actions.current_environment_name):
            script_scope.setdefault(LAYOUT_CONSTRUCTION_PROCESS_ID_VAR_NAME, script.ScriptVariable(script.wrap_python_value(construct_ctx.layout_process_id)))
            return actions.script_runner.run_async(s)
        else:
            uid, *_ = actions.enqueue_script(s, action.script_environment)
            async def _wait():
                await actions.wait_script_finish_async(uid)
            return _wait()
        

class ConstructProcess:
    def __init__(self, layout:Layout, element:LayoutElement, tree:bs4.BeautifulSoup|None, loop:asyncio.AbstractEventLoop):
        self.layout = layout
        self.element = element
        self.tree = tree
        self.loop = loop
        self.done = asyncio.Event()
        self.success = False

    def finish(self, success:bool):
        if not self.done.is_set():
            self.success = success
            self.loop.call_soon_threadsafe(self.done.set)

_construct_processes:dict[UUID, ConstructProcess] = {}
_construct_processes_lock = asyncio.Lock()

async def get_construction_process(process_id:UUID):
    async with _construct_processes_lock:
        return _construct_processes.get(process_id, None)
    
async def remove_construction_process(process_id:UUID):
    async with _construct_processes_lock:
        return _construct_processes.pop(process_id, None)


def load_layout_html(path:str)->bs4.BeautifulSoup:
    if os.path.isfile(path):
        with open(path) as f:
            c = f.read()
    else:
        c = ""
    return bs4.BeautifulSoup(c, "html.parser")

def load_layout_meta(path:str)->Layout|None:
    if os.path.isfile(path):
        with open(path) as f:
            layout_data = json.load(f)
        layout = Layout.__new__(Layout)
        layout.__setstate__(layout_data)
        return layout

async def _construct(tree:bs4.BeautifulSoup, layout:Layout, args:dict[str]):
    loop = asyncio.get_running_loop()

    futures = []
    processes:list[ConstructProcess] = []

    async def process_wait(process_id:UUID, process:ConstructProcess, element:LayoutElement):
        try:
            c = element.construct.handle(LayoutElementConstructContext(layout, element, args, process_id))
            if inspect.isawaitable(c):
                await c
        finally:
            await remove_construction_process(process_id)
            process.finish(False) #if resolve is not explicitly called, fail

    for element in layout.elements.values():
        if element.construct is None:
            continue
        
        process_id = uuid4()
        process = ConstructProcess(layout, element, tree, loop)

        processes.append(process)
            
        async with _construct_processes_lock:
            _construct_processes[process_id] = process

        futures.append(asyncio.ensure_future(process_wait(process_id, process, element), loop=loop))

    for process in processes:
        await process.done.wait()
        if not process.success:
            ... #TODO exception failed to construct for element
    
    return tree

async def construct(tree:bs4.BeautifulSoup, layout:Layout, args:dict[str])->str:
    return (await _construct(tree, layout, args)).prettify()