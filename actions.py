import asyncio
import base64
import contextlib
import copy
import datafile
import exiting
import inspect
import json
import logenv
import os
import pickle
import threading
import tronix
from typing import Any, Iterable, Self, Union
from uuid import UUID, uuid4

ACTIONS_PATH = datafile.makepath("actions.json")
TRIGGERS_PATH = datafile.makepath("triggers.json")

ACTION_RETURN_VALUE_VAR_NAME = "SZBOT_ACTION_RETURN_VALUE"

class ActionRequestedValue:
    def __init__(self, name:str, t:type, required:bool=True):
        self.name = name
        self.type = t
        self.required = required
    
    def __getstate__(self):
        t = tronix.script.DATA_TYPE_TABLE.get(self.type, None)
        if t is None:
            t = tronix.script.wrap_python_type(self.type)
        return {
            "name": self.name,
            "type" : t.name,
            "required": self.required
        }
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.type = tronix.script.name_to_type(d["type"]).inner
        self.required = bool(d["required"])

class ActionValueMapping:
    def fill_values(self, *args, **kwargs)->dict[str]:
        raise NotImplementedError
    
    def __getstate__(self):
        raise NotImplementedError

    def __setstate__(self, d):
        raise NotImplementedError


TRIGGER_ABSTAIN = object()

class Trigger:

    TYPE_NAME:str = TRIGGER_ABSTAIN

    def __init_subclass__(cls):
        super().__init_subclass__()
        tn = getattr(cls, "TYPE_NAME", None)
        if tn is TRIGGER_ABSTAIN:
            return
        assert isinstance(tn, str) and tn not in _trigger_types, "Trigger TYPE_NAME must be a unique name (str) to associate with this trigger type."
        assert not (cls.__getstate__ is Trigger.__getstate__ or cls.__setstate__ is Trigger.__setstate__), "Trigger must have __getstate__ and __setstate__."
        _trigger_types[tn] = cls
        _trigger_cache[cls] = _trigger_cache_entry()


    @classmethod
    def load_all(cls):
        ce = _trigger_cache.get(cls, None)
        assert ce is not None, "Can only load and save triggers with TYPE_NAME."
        _trigger_update_cache()
        rtv:dict[str, Self] = {}
        if ce.enabled:
            d = ce.get()
            for k, td in d.items():
                td["name"] = k
                t = cls.__new__(cls)
                t.__setstate__(td)
                rtv[t.name] = t
        return rtv

    @classmethod
    def save_all(cls, triggers:Iterable[Self], clean_save:bool=True):
        ce = _trigger_cache.get(cls, None)
        assert ce is not None, "Can only load and save triggers with TYPE_NAME."
        _trigger_update_cache()
        if ce.enabled:
            d = {}
            for t in triggers:
                t.__save(d)
            ce.set(d, clean_save)
            
    @classmethod
    def enabled(cls, value:bool):
        ce = _trigger_cache.get(cls, None)
        assert ce is not None, "Can only enable/disable triggers with TYPE_NAME."
        ce.enabled = bool(value)

    def __init__(self, name:str):
        self.name = name

    def __getstate__(self)->dict[str]:
        raise NotImplementedError
    
    def __setstate__(self, d:dict[str]):
        raise NotImplementedError

    def handle(self, *args):
        raise NotImplementedError
    
    def save(self):
        ce = _trigger_cache.get(type(self), None)
        assert ce is not None, "Can only load and save triggers with TYPE_NAME."
        _trigger_update_cache()
        if ce.enabled:
            d = ce.get()
            self.__save(d)
            if ce.set(d, clean=False):
                _trigger_save()
        else:
            return {}

    def __save(self, d:dict[str, dict[str]]):
        x = self.__getstate__()
        n = x.pop("name", self.name)
        d[n] = x

class _trigger_cache_entry:
    def __init__(self, cache:dict[str, dict[str]]|None=None, lock:Union[threading.Lock, None]=None, enabled:bool=False):
        self.cache:dict[str, dict[str]] = {} if cache is None else cache
        self.lock = threading.Lock() if lock is None else lock
        self.enabled = enabled

    def get(self):
        with self.lock:
            return copy.deepcopy(self.cache)
    
    def set(self, value, clean:bool=True): #value must be of type dict[str, dict[str]]
        if isinstance(value, dict):
            pop_keys = []
            for k, v in value.items():
                if not (isinstance(k, str) and isinstance(v, dict) and all(isinstance(vk, str) for vk in v.keys())):
                    pop_keys.append(k)
            for k in pop_keys:
                del value[k]
        else:
            return False
        with self.lock:
            if clean:
                self.cache = value
            else:
                self.cache.update(value)
        return True

_trigger_mtime:float = 0.0
_trigger_types:dict[str, type[Trigger]] = {}
_trigger_cache:dict[type[Trigger], _trigger_cache_entry] = {}

def _trigger_update_cache():
    global _trigger_mtime

    if not os.path.isfile(TRIGGERS_PATH):
        return
    mtime = os.stat(TRIGGERS_PATH).st_mtime
    if mtime == _trigger_mtime:
        return
    _trigger_mtime = mtime
    with open(TRIGGERS_PATH) as f:
        c = json.load(f)
    if isinstance(c, dict):
        for tn, triggers in c.items():
            tt = _trigger_types.get(tn, None)
            if tt is None:
                continue
            ce = _trigger_cache[tt]
            ce.set(triggers)

def _trigger_save():
    global _trigger_mtime

    d = {tt.TYPE_NAME:ce.cache for tt,ce in _trigger_cache.items()}
    c = json.dumps(d, indent=4, ensure_ascii=False)

    with open(TRIGGERS_PATH, "w") as f:
        f.write(c)

    _trigger_mtime = os.stat(TRIGGERS_PATH).st_mtime

def create_triggers_merge_function[T:Trigger, U:Trigger, V:Trigger](t_type:type[T], at_type:type[U], callbacks:dict[str, V]):
    def merge()->dict[str, T]:
        d = callbacks.copy()
        d.update(at_type.load_all())
        logenv.main.debug(d)
        return d
    return merge

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
            "requested_values": {v.name:v.__getstate__() for v in self.requested_values.values()},
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
    
    def is_script_environment_local(self):
        return self.script_environment is None or match_environment_name(self.script_environment, current_environment_name)

class _env_switch_done_entry:
    def __init__(self, loop:asyncio.AbstractEventLoop=None):
        self.aevent = asyncio.Event()
        self.tevent = threading.Event()
        self.success = None
        self.return_value:tronix.script.ScriptValue|None = None
        self._loop = loop
    
    def mark_done(self, success:bool, return_value:tronix.script.ScriptValue|None=None):
        self.success = success
        self.return_value = return_value
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

def _enqueue_script(uid:UUID, environment:str, s:tronix.Script, is_done:_env_switch_done_entry):
    data = (uid, environment, s, is_done)
    with _env_switch_queue_lock:
        q = _env_switch_queue.get(environment,None)
        if q is not None:
            _env_switch_done[uid] = is_done
            q.append(data)
    return data

def enqueue_script(s:tronix.Script, environment:str|None=None, uid:UUID|None=None):
    if uid is None:
        uid = uuid4()
    if environment is None:
        assert isinstance(current_environment_name, str), "current_environment_name must be set"
        environment = current_environment_name
    elif "@" not in environment:
        evx = generate_environment_name(environment)
        if evx == current_environment_name:
            environment = evx
        with _env_switch_queue_lock:
            if evx in _env_switch_queue:
                environment = evx
            else:
                for env in _env_switch_queue:
                    if env.startswith(environment):
                        environment = env
                        break
    is_done = _env_switch_done_entry()
    return _enqueue_script(uid, environment, s, is_done)

def wait_script_finish(uid:UUID, timeout:float|None=None):
    de = _env_switch_done.get(uid, None)
    if de is None:
        return None, None
    if de.wait(timeout=timeout):
        del _env_switch_done[uid]
    return de.success, de.return_value

async def wait_script_finish_async(uid:UUID, timeout:float|None=None):
    de = _env_switch_done.get(uid, None)
    if de is None:
        return None, None
    if de._loop is None:
        de._loop = asyncio.get_event_loop()
    if await de.wait_async(timeout=timeout, loop=asyncio.get_running_loop()):
        del _env_switch_done[uid]
    return de.success, de.return_value

async def _run_script(uid:UUID, s:tronix.Script, *x):
    success = False
    try:
        await script_runner.run_async(s)
    except Exception as e:
        #TODO handle exceptions
        #TODO be more helpful in the human text, especially if its a script exception and not a python one
        logenv.main.error_exception(
            e,
            f"Script {{uid}} encountered an exception:\n{logenv.EXCEPTION_TRACEBACK}",
            human_text="Script encountered an error",
            uid=str(uid)
        )
    else:
        success = True
    logenv.main.debug("_run_script success: {uid} {success}", uid=uid, success=success)
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
    c = json.dumps({action.name:action.__getstate__() for action in table.values()}, indent=4, ensure_ascii=False)
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


def extra_data_serialize(d:dict[str], type_str:bool=True):
    sd = {}
    for k,v in d.items():
        value = tronix.script.wrap_python_value(v)
        sd[k] = tronix.utils._serialized_value.serialize(value, type_str=type_str).__getstate__()
    return sd

def extra_data_deserialize(d:dict[str,dict[str]]):
    dsd = {}
    for k,v in d.items():
        sv = tronix.utils._serialized_value.__new__(tronix.utils._serialized_value)
        sv.__setstate__(v)
        dsd[k] = sv.deserialize()
    return dsd

shared_loop = None

def run_shared_loop():
    ready = threading.Event()
    def _thread():
        global shared_loop
        shared_loop = asyncio.new_event_loop()
        @exiting.register_cleanup_listener
        def _cleanup(ctx):
            exiting.unregister_cleanup_listener(_cleanup)
            logenv.main.info("cleaning up shared loop")
            shared_loop.call_soon_threadsafe(shared_loop.stop)
            logenv.main.info("cancelling shared loop tasks")
            pending = asyncio.all_tasks(shared_loop)
            for task in pending:
                task.cancel()
            logenv.main.info(f"cancelled {len(pending)} shared loop task{"s"*bool(len(pending)-1)}")
            logenv.main.info("cleaned up shared loop")
        ready.set()
        shared_loop.run_forever()
        exiting.unregister_cleanup_listener(_cleanup)

    thread = threading.Thread(target=_thread)
    thread.start()
    return thread, ready

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
    global _run_trigger_loop
    _run_trigger_loop = asyncio.get_running_loop()
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
            _run_triggers_futures[uid] = asyncio.ensure_future(_run_triggers(uid, triggers), loop=_run_trigger_loop)

def run_triggers_thread_handler():
    _run_triggers_queue_ready.clear()
    future = asyncio.run_coroutine_threadsafe(run_triggers_loop(), shared_loop)
    future.result()

def stop_trigger_loop():
    global _run_trigger
    _run_trigger = False
    _run_trigger_loop.call_soon_threadsafe(_run_triggers_queue_ready.set)

def enqueue_triggers(triggers:list[tuple[Trigger, tuple, dict]]):
    with _run_triggers_queue_lock:
        _run_triggers_queue.extend(triggers)
        _run_trigger_loop.call_soon_threadsafe(_run_triggers_queue_ready.set)

def serialize_script_return_value(script:tronix.Script):
    rtvar = script.scope.get(ACTION_RETURN_VALUE_VAR_NAME, None)
    if isinstance(rtvar, tronix.script.ScriptVariable):
        return base64.b64encode(pickle.dumps(tronix.utils.serialize_value(rtvar.get()))).decode("utf-8")
    else:
        return None
    
def deserialize_script_return_value(s:str|None):
    if not isinstance(s, str):
        return None
    return tronix.utils.deserialize_value(pickle.loads(base64.b64decode(s.encode("utf-8"))))