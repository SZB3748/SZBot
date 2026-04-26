import asyncio
import contextlib
import datafile
import inspect
import json
import os
import threading
import traceback
import tronix
from typing import Any
from uuid import UUID, uuid4

ACTIONS_PATH = datafile.makepath("actions.json")

class ActionRequestedValue:
    def __init__(self, name:str, t:type, required:bool=True):
        self.name = name
        self.type = t
        self.required = required
    
    def __getstate__(self):
        if self.type in tronix.script.DATA_TYPE_TABLE:
            t = tronix.script.DATA_TYPE_TABLE[self.type]
        else:
            t = tronix.script.wrap_python_type(self.type)
        return {
            "name": self.name,
            "type" : t.name,
            "required": self.required
        }
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.type = tronix.script._map_name_to_type(d["type"]).inner
        self.required = bool(d["required"])

class ActionValueMapping:
    def fill_values(self, *args, **kwargs)->dict[str]:
        raise NotImplementedError
    
    def __getstate__(self):
        raise NotImplementedError

    def __setstate__(self, d):
        raise NotImplementedError

class Trigger:
    def handle(self, *args):
        raise NotImplementedError

class Action:
    def __init__(self, name:str, script:str, requested_values:dict[str, ActionRequestedValue]|None=None, script_environment:str|None=None):
        self.name = name
        self.script = script
        self.requested_values = {} if requested_values is None else requested_values
        self.script_environment = script_environment

    def __getstate__(self):
        return {
            "name": self.name,
            "script": self.script,
            "requested_values": {k:v.__getstate__() for k,v in self.requested_values.items()},
            "script_environment": self.script_environment
        }
    
    def __setstate__(self, d:dict[str]):
        if "name" in d:
            self.name = str(d["name"])
        if "script" in d:
            self.script = str(d["script"])
        if "requested_values" in d:
            self.requested_values = r = {}
            xr:dict[str,dict[str]] = d["requested_values"]
            for k,v in xr.items():
                r[k] = rv = ActionRequestedValue.__new__(ActionRequestedValue)
                rv.__setstate__(v)
        script_environment = d["script_environment"]
        self.script_environment = None if script_environment is None else str(script_environment)

    def collect_script_values(self, mapped_values:dict[str])->tronix.script.Namespace:
        rtv = {}
        for rv in self.requested_values.values():
            if rv.name in mapped_values:
                value = mapped_values[rv.name]
                if isinstance(value, tronix.script.ScriptValue):
                    if issubclass(value.type.inner, rv.type):
                        rtv[rv.name] = tronix.script.ScriptVariable(value)
                        continue
                if isinstance(value, rv.type):
                    rtv[rv.name] = tronix.script.ScriptVariable(tronix.script.wrap_python_value(value))
                    continue
                ... #TODO error type doesnt match
            elif rv.required:
                ... #TODO error missing required value
        return rtv

class _env_switch_done_entry:
    def __init__(self, loop:asyncio.AbstractEventLoop=None):
        self.aevent = asyncio.Event()
        self.tevent = threading.Event()
        self.success = None
        self._loop = loop
    
    def mark_done(self, success:bool):
        self.success = success
        if self._loop is None:
            self.aevent.set()
        else:
            self._loop.call_soon_threadsafe(self.aevent.set)

    def wait(self, timeout:float|None=None):
        return self.tevent.wait(timeout=timeout)

    async def wait_async(self, timeout:float|None=None, loop:asyncio.AbstractEventLoop=None):
        if loop is not None:
            self._loop = loop
        if timeout is None:
            return await self.aevent.wait()
        else:
            with contextlib.suppress(asyncio.TimeoutError):
                return await asyncio.wait_for(self.aevent.wait(), timeout=timeout)
            return False

_env_switch_queue:dict[str, list[tuple[UUID, str, tronix.Script|dict[str], _env_switch_done_entry]]] = {}
_env_switch_queue_lock = threading.Lock()
_env_switch_done:dict[UUID,_env_switch_done_entry] = {}

def enqueue_script(s:tronix.Script, environment:str|None=None, uid:UUID|None=None):
    if uid is None:
        uid = uuid4()
    if environment is None:
        assert isinstance(current_environment_name, str), "current_environment_name must be set"
        environment = current_environment_name
    elif "@" not in environment:
        evx = generate_environment_name(environment)
        with _env_switch_queue_lock:
            if evx in _env_switch_queue:
                environment = evx
            else:
                for env in _env_switch_queue:
                    if env.startswith(environment):
                        environment = env
                        break
    is_done = _env_switch_done_entry()
    data = (uid, environment, s, is_done)
    with _env_switch_queue_lock:
        q = _env_switch_queue.get(environment,None)
        if q is not None:
            _env_switch_done[uid] = is_done
            q.append(data)
    return data

def wait_script_finish(uid:UUID, timeout:float|None=None)->bool|None:
    de = _env_switch_done.get(uid, None)
    if de is None:
        return None
    if de.wait(timeout=timeout):
        del _env_switch_done[uid]
    return de.success

async def wait_script_finish_async(uid:UUID, timeout:float|None=None)->bool|None:
    de = _env_switch_done.get(uid, None)
    if de is None:
        return None
    if de._loop is None:
        de._loop = asyncio.get_event_loop()
    if await de.wait_async(timeout=timeout, loop=asyncio.get_running_loop()):
        del _env_switch_done[uid]
    return de.success

async def _run_script(uid:UUID, s:tronix.Script, *x):
    success = False
    try:
        await script_runner.run_async(s)
    except Exception as e:
        #TODO handle exceptions
        traceback.print_exception(e)
        import tronix.exceptions
        if isinstance(e, tronix.exceptions.TExpectedEvaluable):
            print(e.target)
    else:
        success = True
    return uid, success, *x

async def run_scripts(*pairs:tuple[UUID,tronix.Script,str]):
    return await asyncio.gather(*(_run_script(*pair) for pair in pairs))

script_runner = tronix.utils.ScriptRunner()
current_environment_name:str = None

def generate_environment_name(name:str, hostname:str|None=None):
    import socket
    if hostname is None:
        hostname = socket.gethostname()
    return f"{name}@{hostname}"

def match_environment_name(specified:str, match_against:str):
    assert "@" in match_against, f"match_against must be a full scripting environment name, got {match_against}"
    if "@" not in specified:
        specified = generate_environment_name(specified)
    return specified == match_against

def load_action_table(path:str=None)->dict[str, Action]:
    if path is None:
        path = ACTIONS_PATH
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        d:dict[str,dict[str]] = json.load(f)
    rtv = {}
    for k,v in d.items():
        rtv[k] = action = Action.__new__(Action)
        action.__setstate__(v)
    return rtv

def save_action_table(table:dict[str, Action], path:str=None):
    c = json.dumps({action.name:action.__getstate__() for action in table.values()}, indent=4)
    with open(ACTIONS_PATH if path is None else path, "w") as f:
        f.write(c)

class get_action:
    NO_DEFAULT = object()

    def __init__(self, name:str, default:Any=NO_DEFAULT, update:bool=True, path:str=ACTIONS_PATH):
        self.name = name
        self.default = default
        self.update = update
        self.path = path
        self._table = None
        self._action = None

    def __enter__(self):
        self._table = load_action_table(path=self.path)
        if self.default is self.NO_DEFAULT:
            self._action = self._table[self.name]
        else:
            self._action = self._table.get(self.name, self.default)
        return self._action

    def __exit__(self, exc_type, exc, tb):
        if self.update and isinstance(self._action, Action):
            if self._action.name != self.name:
                if self._action is self._table.get(self.name, None):
                    del self._table[self.name]
                self._table[self._action.name] = self._action
            save_action_table(self._table, path=self.path)

def check_script(raw:str):
    try:
        script_runner._prep(raw)
    except tronix.exceptions.TronixException as e:
        return tronix.utils.generate_exception_help(raw, e)


def extra_data_serialize(d:dict[str]):
    sd = {}
    for k,v in d.items():
        value = tronix.script.wrap_python_value(v)
        sd[k] = state = tronix.utils._serialized_value.serialize(value).__getstate__()
        state["t"] = value.type.name
    return sd

def extra_data_deserialize(d:dict[str,dict[str]]):
    dsd = {}
    for k,v in d.items():
        sv = tronix.utils._serialized_value.__new__(tronix.utils._serialized_value)
        sv.__setstate__(v)
        dt = tronix.script._map_name_to_type(sv.t)
        if dt is None:
            dsd[k] = sv.v
        else:
            sv.t = dt
            dsd[k] = sv.deserialize()
    return dsd

_run_trigger = True
_run_trigger_loop = None
_run_triggers_queue:list[tuple[Trigger, tuple, dict]] = []
_run_triggers_queue_lock = threading.Lock()
_run_triggers_queue_ready = asyncio.Event()

_run_triggers_futures:dict[UUID, asyncio.Future] = {}
_run_triggers_futures_lock = asyncio.Lock()

async def _run_triggers(id, triggers:list[tuple[Trigger, tuple, dict]]):
    global _run_trigger
    try:
        await asyncio.gather(*(c for kbt in triggers if inspect.isawaitable(c:=kbt[0].handle(*kbt[1], **kbt[2]))))
    except KeyboardInterrupt:
        _run_trigger = False
        async with _run_triggers_futures_lock:
            _run_triggers_queue_ready.set()
    finally:
        async with _run_triggers_futures_lock:
            _run_triggers_futures.pop(id,None)

async def run_triggers_loop():
    _loop = asyncio.get_running_loop()
    while _run_trigger:
        await _run_triggers_queue_ready.wait()
        if not _run_trigger:
            return
        with _run_triggers_queue_lock:
            triggers = _run_triggers_queue.copy()
            _run_triggers_queue.clear()
            _run_triggers_queue_ready.clear()
        uid = uuid4()
        async with _run_triggers_futures_lock:
            _run_triggers_futures[uid] = asyncio.ensure_future(_run_triggers(uid, triggers), loop=_loop)

def run_triggers_thread_handler():
    global _run_trigger_loop
    _run_triggers_queue_ready.clear()
    _run_trigger_loop = loop = asyncio.new_event_loop()
    loop.run_until_complete(run_triggers_loop())

def stop_trigger_loop():
    global _run_trigger
    _run_trigger = False
    _run_trigger_loop.call_soon_threadsafe(_run_triggers_queue_ready.set)

def enqueue_triggers(triggers:list[tuple[Trigger, tuple, dict]]):
    with _run_triggers_queue_lock:
        _run_triggers_queue.extend(triggers)
        _run_trigger_loop.call_soon_threadsafe(_run_triggers_queue_ready.set)