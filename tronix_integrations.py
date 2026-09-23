import actions
import asyncio
import config
from datetime import datetime, timedelta
from overlays import tronix_integrations as oti
import plugins
import requests
import runtime as rt
import sys
from tronix import duration_types as durtypes, exceptions, json_proxy, script, script_builtins as builtins, utils
import twitch.tronix_integrations as tti
from typing import Any, Callable
import uuid


s = requests.Session()

activation_handlers:dict[str, Callable[[], None]] = {}
deactivation_handlers:dict[str, Callable[[], None]] = {}

class _action_requested_value_parameter(builtins._pair[str, Any]):
    pass

class _action_function_parameters:
    def __init__(self):
        self.params:list[utils.ScriptFunctionParam|_action_requested_value_parameter] = []
        self.names:dict[str,str] = {} #param --> scope

    def add_parameter(self, param:utils.ScriptFunctionParam, maps_to:str|None=None):
        if param.name in self.names:
            raise exceptions.TRBadValue(f"parameter name is already used for this function: {param.name}")
        self.params.append(param)
        self.names[param.name] = param.name if maps_to is None else maps_to

    def add_value_request(self, rv:actions.ActionRequestedValue, param_name:str|None=None, default=utils._PARAM_NO_DEFAULT):
        if param_name is None:
            param_name = rv.name
        if param_name in self.names:
            raise exceptions.TRBadValue(f"parameter name is already used for this function: {param_name}")
        self.params.append(utils.ScriptFunctionParam(param_name, [script.wrap_python_type(rv.type)], default=default))
        self.names[param_name] = rv.name

    def add_value_request_by_name(self, name:str, param_name:str|None=None, default=utils._PARAM_NO_DEFAULT):
        if param_name is None:
            param_name = name
        if param_name in self.names:
            raise exceptions.TRBadValue(f"parameter name is already used for this function: {param_name}")
        self.params.append(_action_requested_value_parameter(param_name, default))
        self.names[param_name] = name

    def generate_param_set(self, action:actions.Action, pass_ctx:bool=False, pass_fit:bool=True):
        params = []
        for param in self.params:
            if isinstance(param, utils.ScriptFunctionParam):
                params.append(param)
            else:
                rvname = self.names[param.first]
                rv = action.requested_values.get(rvname, None)
                if rv is None:
                    raise exceptions.TRBadValue(f"Given action does not have the requested value: {rvname}")
                params.append(utils.ScriptFunctionParam(param.first, [script.wrap_python_type(rv.type)], default=param.second))
        return utils.ScriptFunctionParamSet(params, pass_ctx=pass_ctx, pass_fit=pass_fit)

    def __getitem__(self, key:int):
        return self.params[key]

    def __iter__(self):
        return iter(self.params)

    def __contains__(self, item):
        return item in self.params


class _ScheduledAction:
    __slots__ = "_task", "_scheduled_at", "_scheduled_for", "_wait_for_dur", "_wait_for"

    def __init__(self, uid:uuid.UUID, task:asyncio.Task, scheduled_at:datetime, wait_for:float):
        self._uid = uid
        self._task = task
        self._scheduled_at = scheduled_at
        self._scheduled_for = scheduled_at + timedelta(seconds=self._wait_for)
        self._wait_for_dur = durtypes._complex_duration(secs=wait_for).simplify()
        self._wait_for = wait_for

    def remaining_time(self):
        now = datetime.now()
        if now >= self._scheduled_for:
            return 0
        else:
            return self._wait_for - (datetime.now()-self._scheduled_at).total_seconds()


_ActionFunctionParametersTypeAttrs = utils.ScriptAttributeHandler[_action_function_parameters, int]()
@_ActionFunctionParametersTypeAttrs.enforce_child_attrs()
@_ActionFunctionParametersTypeAttrs.attach
class _ActionFunctionParametersType(script.ScriptDataType[_action_function_parameters]):

    construct = f_construct = utils.ScriptFunction()

    attrs = _ActionFunctionParametersTypeAttrs
    attrs.entry("length").readonly(lambda o, n: script.wrap_python_value(len(o.inner.params)))


_ScheduledActionTypeAttrs = utils.ScriptAttributeHandler[_ScheduledAction,Any]()
class _ScheduledActionType(script.ScriptDataType[_ScheduledAction]):

    attrs = _ScheduledActionTypeAttrs
    attrs.entry("id").readonly(lambda o,n: script.wrap_python_value(o.inner._uid))
    attrs.entry("scheduled_at").readonly(lambda o,n: script.wrap_python_value(o.inner._scheduled_at))
    attrs.entry("scheduled_for").readonly(lambda o,n: script.wrap_python_value(o.inner._scheduled_for))
    attrs.entry("wait_for").readonly(lambda o,n: script.wrap_python_value(o.inner._wait_for_dur))
    attrs.entry("remaining_time").readonly(lambda o,n: script.wrap_python_value(durtypes._complex_duration(secs=o.inner.remaining_time()).simplify()))

    def repr(self, value):
        return script.ScriptValue(builtins.String, f"<ScheduledAction {str(value.inner._uid)} scheduled for {(value.inner._scheduled_for).isoformat()} ({value.inner.remaining_time()} seconds remaining)>")


_ActionRequestedValueTypeAttrs = utils.ScriptAttributeHandler[actions.ActionRequestedValue,Any](no_subscripting=True)
@_ActionRequestedValueTypeAttrs.enforce_child_attrs()
@_ActionRequestedValueTypeAttrs.attach
class _ActionRequestedValueType(script.ScriptDataType[actions.ActionRequestedValue]):
    
    construct = f_construct = utils.ScriptFunction()

    attrs = _ActionRequestedValueTypeAttrs
    attrs.entry("name").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter(str, utils.SimpleSetAttribute())).nodel()
    attrs.entry("type").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter(type, utils.SimpleSetAttribute())).nodel()
    attrs.entry("bool").getter(utils.SimpleGetAttribute()).setter(utils.TypedSetter(bool, utils.SimpleSetAttribute())).nodel()

_ActionValueMappingTypeAttrs = utils.ScriptAttributeHandler[actions.ActionValueMapping,Any]()
@_ActionValueMappingTypeAttrs.enforce_child_attrs()
@_ActionValueMappingTypeAttrs.attach
class _ActionValueMappingType(script.ScriptDataType[actions.ActionValueMapping]):
    
    attrs = _ActionRequestedValueTypeAttrs

_ActionTriggerTypeAttrs = utils.ScriptAttributeHandler[actions.Trigger,Any]()
@_ActionTriggerTypeAttrs.enforce_child_attrs()
@_ActionTriggerTypeAttrs.attach
class _ActionTriggerType(script.ScriptDataType[actions.Trigger]):
    
    attrs = _ActionTriggerTypeAttrs

_ActionTypeAttrs = utils.ScriptAttributeHandler[actions.Action,Any]()
@_ActionTypeAttrs.enforce_child_attrs()
@_ActionTypeAttrs.attach
class _ActionType(script.ScriptDataType[actions.Action]):

    attrs = _ActionTypeAttrs
    attrs.entry("name").readonly(utils.SimpleGetAttribute())
    attrs.entry("script").readonly(utils.SimpleGetAttribute())
    attrs.entry("requested_values").readonly(utils.SimpleGetAttribute())
    attrs.entry("script_environment").readonly(utils.SimpleGetAttribute())

def config_mtime_remote():
    r = s.head(f"http{"s"*rt.remote_secure}://{rt.remote_addr[0]}:{rt.remote_addr[1]}/api/configs")
    r.raise_for_status()
    return int(r.headers["MTIME"])

def config_load_remote():
    r = s.get(f"http{"s"*rt.remote_secure}://{rt.remote_addr[0]}:{rt.remote_addr[1]}/api/configs")
    r.raise_for_status()
    return r.json()

def config_save_remote(data):
    r = s.put(f"http{"s"*rt.remote_secure}://{rt.remote_addr[0]}:{rt.remote_addr[1]}/api/configs", json=data)
    return r.ok

def scriptend_save_config(s:script.Script):
    config_proxy.merge_changes()

config_proxy = json_proxy.JsonProxyRoot(config.CONFIG_FILE)

ActionRequestedValue = _ActionRequestedValueType("ActionRequestedValue", actions.ActionRequestedValue, builtins.BASE_TYPE)
ActionValueMapping = _ActionValueMappingType("ActionValueMapping", actions.ActionValueMapping, builtins.BASE_TYPE)
ActionTrigger = _ActionTriggerType("ActionTrigger", actions.Trigger, builtins.BASE_TYPE)
Action = _ActionType("Action", actions.Action, builtins.BASE_TYPE)
ActionFunctionParameters = _ActionFunctionParametersType("ActionFunctionParameters", _action_function_parameters, builtins.BASE_TYPE)
ScheduledAction = _ScheduledActionType("ScheduledAction", _ScheduledAction, builtins.BASE_TYPE)
ActionRequestedValueParameter = builtins.pair_alias_subtype("ActionValueRequestParameter", ["name"], ["default"], _action_requested_value_parameter)

@_ActionRequestedValueType.f_construct.overload(("name", builtins.String), ("type", builtins.Type), ("required", builtins.Bool, builtins.true))
def ActionRequestedValue_constructor(self:_ActionRequestedValueType, name:script.ScriptVariable[str], type:script.ScriptVariable[type], required:script.ScriptVariable[bool]):
    return script.ScriptValue(self, actions.ActionRequestedValue(name.get().inner, type.get().inner, required.get().inner))

f_get_action = utils.ScriptFunction()
f_run_action = utils.ScriptFunction()
f_schedule_action = utils.ScriptFunction()
f_cancel_scheduled_action = utils.ScriptFunction()
f_make_function_for_action = utils.ScriptFunction()
f_set_action_return_value = utils.ScriptFunction()
f_save = utils.ScriptFunction()
f_append = utils.ScriptFunction()
f_get_current_host_url = utils.ScriptFunction()
f_get_remote_host_url = utils.ScriptFunction()
f_iterate_over = utils.ScriptFunction()

@f_get_action.overload(("name", builtins.String))
async def get_action(name:script.ScriptVariable[str]):
    table = actions.load_action_table()
    return script.wrap_python_value(table.get(name.get().inner, None))

async def _run_action(a:actions.Action, passed_scope:dict[str]):
    s = script.Script(a.script, a.collect_script_values(passed_scope))
    if a.script_environment is None or actions.match_environment_name(a.script_environment, actions.current_environment_name):
        await actions.script_runner.run_async(s) #TODO get current script runner (somehow)
        rtvar = s.scope.get(actions.ACTION_RETURN_VALUE_VAR_NAME, None)
        if isinstance(rtvar, script.ScriptVariable):
            return rtvar.get()
    else:
        uid, *_ = actions.enqueue_script(s, a.script_environment)
        success, return_value = await actions.wait_script_finish_async(uid)
        if success:
            return return_value

@f_run_action.overload(("action", [Action, builtins.String]), ("scope", [builtins.MapOf(builtins.String), builtins.NullType], None))
async def run_action(action:script.ScriptVariable[actions.Action|str], scope:script.ScriptVariable[dict[str]|None]):
    table = actions.load_action_table()
    av = action.get()
    if av.type.issubtype(Action):
        assert isinstance(av.inner, actions.Action)
        a = av.inner
    else:
        assert isinstance(av.inner, str)
        a = table.get(av.inner, None)
        if a is None:
            raise actions.ActionNotFound(f"Could not find action: {av.inner}", action_name=av.inner)
    
    passed_scope = {} if (scope_inner := scope.get().inner) is None else scope_inner.copy()
    return await _run_action(a, passed_scope)

    

_scheduled_actions:dict[uuid.UUID, _ScheduledAction] = {}
_running_scheduled_actions:dict[uuid.UUID, asyncio.Task] = {}

@f_schedule_action.overload(("action", [Action, builtins.String]), ("wait_for", [builtins.Duration, builtins.ComplexDuration]), ("scope", [builtins.MapOf(builtins.String), builtins.NullType], None))
def schedule_action(action:script.ScriptVariable[actions.Action|str], wait_for:script.ScriptVariable[durtypes._duration|durtypes._complex_duration], scope:script.ScriptVariable[dict[str]|None]):
    table = actions.load_action_table()
    av = action.get()
    if av.type.issubtype(Action):
        assert isinstance(av.inner, actions.Action)
        a = av.inner
    else:
        assert isinstance(av.inner, str)
        a = table.get(av.inner, None)
        if a is None:
            raise actions.ActionNotFound(f"Could not find action: {av.inner}", action_name=av.inner)

    d = wait_for.get().inner
    if isinstance(d, durtypes._complex_duration):
        secs = d.as_seconds().x
    else:
        secs = d.x
    passed_scope = {} if (scope_inner := scope.get().inner) is None else scope_inner.copy()

    uid = uuid.uuid4()
    sch_a = _ScheduledAction(uid, asyncio.ensure_future(_wait_action(), loop=asyncio.get_running_loop()), datetime.now().astimezone(), secs)

    async def _ra(uid:uuid.UUID):
        try:
            await _run_action(a, passed_scope)
        finally:
            _running_scheduled_actions.pop(uid,None)

    async def _wait_action():
        sch = None
        try:
            await asyncio.sleep(sch_a.remaining_time())
            sch = _scheduled_actions.pop(uid, None)
            if sch is not None:
                _running_scheduled_actions[uid] = asyncio.ensure_future(_ra(uid), loop=asyncio.get_running_loop())
        finally:
            _scheduled_actions.pop(uid,None)

    return script.wrap_python_value(sch_a)

@f_cancel_scheduled_action.overload(("scheduled_action", [builtins.UUID, ScheduledAction]))
def cancel_scheduled_action(scheduled_action:script.ScriptVariable[uuid.UUID|_ScheduledAction]):
    sch_a = scheduled_action.get()
    if sch_a.type.issubtype(ScheduledAction):
        uid:uuid.UUID = sch_a.inner._uid
    else:
        uid:uuid.UUID = sch_a.inner
    sch = _scheduled_actions.pop(uid, None)
    if sch is None:
        return builtins.false
    else:
        sch._task.cancel()
        return builtins.true

@f_make_function_for_action.overload(("name", builtins.String), ("action", [Action, builtins.String]), ("parameters", [ActionFunctionParameters, builtins.NullType], None), pass_ctx=True)
def make_function_for_action(ctx:script.ScriptContext, name:script.ScriptVariable[str], action:script.ScriptVariable[actions.Action|str], parameters:script.ScriptVariable[_action_function_parameters|None]):
    fn = name.get().inner
    if script.RE_NAME.match(fn) is None:
        raise exceptions.TRBadValue(f"Function name is invalid: {fn}")
    
    table = actions.load_action_table()
    av = action.get()
    if av.type.issubtype(Action):
        assert isinstance(av.inner, actions.Action)
        a = av.inner
    else:
        assert isinstance(av.inner, str)
        a = table.get(av.inner, None)
        if a is None:
            raise actions.ActionNotFound(f"Could not find action: {av.inner}", action_name=av.inner)
    ps = parameters.get().inner
    if ps is None:
        pset = utils.ScriptFunctionParamSet([], pass_fit=True)
    else:
        pset = ps.generate_param_set(a, pass_fit=True)

    sf = utils.ScriptFunction()
    async def _szbot_dynamic_action_function(ctx, f, fit:utils.script_function_signature_fit):
        passed_scope = {ps.names[aname]:arg.get().inner for aname, arg in zip(fit.arg_names, fit.args)}
        for kwname, kwarg in fit.kwargs.items():
            passed_scope[ps.names[kwname]] = kwarg.get().inner
        table = actions.load_action_table()
        aa = table.get(a.name, None)
        if aa is None:
            raise actions.ActionNotFound(f"Could not find action: {a.name}", action_name=a.name)
        return await _run_action(aa, passed_scope)

    sf.add_overload(pset, _szbot_dynamic_action_function)
    xf = utils.merge_function(fn, sf, functions=ctx.script.function_table)
    return script.wrap_python_value(len(xf.cbs))



@f_set_action_return_value.overload(("value", builtins.AnyType), pass_ctx=True)
async def set_action_return_value(ctx:script.ScriptContext, value:script.ScriptVariable):
    ns = ctx.stack.find_name(actions.ACTION_RETURN_VALUE_VAR_NAME)
    if ns is None or ns is ctx.script.scope:
        ctx.script.scope[actions.ACTION_RETURN_VALUE_VAR_NAME] = script.ScriptVariable(value.get())
    else:
        ctx.script.scope[actions.ACTION_RETURN_VALUE_VAR_NAME] = ns.pop(actions.ACTION_RETURN_VALUE_VAR_NAME)

@f_get_current_host_url.overload(("schema", builtins.Bool, True), ("address", builtins.Bool, True), ("port", builtins.Bool, True), ("secure", builtins.Bool, False))
def get_current_host_url(schema:script.ScriptVariable[bool], address:script.ScriptVariable[bool], port:script.ScriptVariable[bool], secure:script.ScriptVariable[bool]):
    parts = []
    if schema.get().inner:
        if secure.get().inner:
            parts.append("https://")
        else:
            parts.append("http://")
    if address.get().inner:
        parts.append(rt.host_addr[0])
    if port.get().inner:
        parts.append(f":{rt.host_addr[1]}")
    return script.ScriptValue(builtins.String, "".join(parts))

@f_get_remote_host_url.overload(("schema", builtins.Bool, True), ("address", builtins.Bool, True), ("port", builtins.Bool, True))
def get_remote_host_url(schema:script.ScriptVariable[bool], address:script.ScriptVariable[bool], port:script.ScriptVariable[bool]):
    parts = []
    if schema.get().inner:
        if rt.remote_secure:
            parts.append("https://")
        else:
            parts.append("http://")
    if address.get().inner:
        parts.append(rt.remote_addr[0])
    if port.get().inner:
        parts.append(f":{rt.remote_addr[1]}")
    return script.ScriptValue(builtins.String, "".join(parts))

_ACTION_FUNC_PARAMS_STOP = sys.maxsize
@f_iterate_over.overload(("target", ActionFunctionParameters), ("start", builtins.Integer, 0), ("stop", builtins.Integer, _ACTION_FUNC_PARAMS_STOP), ("step", builtins.Integer, 1))
def iterate_over_action_func_params(target:script.ScriptVariable[_action_function_parameters], start:script.ScriptVariable[int], stop:script.ScriptVariable[int], step:script.ScriptVariable[int]):
    v = start.get().inner
    s = step.get().inner
    return script.wrap_python_value(builtins._sequence_iterator(v-s, v, stop.get().inner, s, target.get().inner))

@f_append.overload(("params", ActionFunctionParameters), ("parameter", builtins.FunctionParameter), ("maps_to", [builtins.String, builtins.NullType], builtins.null))
def append_params_direct(params:script.ScriptVariable[_action_function_parameters], parameter:script.ScriptVariable[utils.ScriptFunctionParam], maps_to:script.ScriptVariable[str|None]):
    params.get().inner.add_parameter(parameter.get().inner, maps_to.get().inner)

@f_append.overload(("params", ActionFunctionParameters), ("requested_value", ActionRequestedValue), ("parameter_name", [builtins.String, builtins.NullType], builtins.null), ("default", builtins.AnyType, utils._PARAM_NO_DEFAULT))
def append_params_rv(params:script.ScriptVariable[_action_function_parameters], requested_value:script.ScriptVariable[actions.ActionRequestedValue], parameter_name:script.ScriptVariable[str|None], default:script.ScriptVariable):
    params.get().inner.add_value_request(requested_value.get().inner, parameter_name.get().inner, default.get().inner)

@f_append.overload(("params", ActionFunctionParameters), ("requested_value_name", builtins.String), ("parameter_name", [builtins.String, builtins.NullType], None), ("default", builtins.AnyType, utils._PARAM_NO_DEFAULT))
def append_params_rvr(params:script.ScriptVariable[_action_function_parameters], requested_value_name:script.ScriptVariable[str], parameter_name:script.ScriptVariable[str|None], default:script.ScriptVariable):
    params.get().inner.add_value_request_by_name(requested_value_name.get().inner, parameter_name.get().inner, default.get().inner)

def activate():

    if rt.core_components.get(plugins.CORE_COMPONENT_API,None) == plugins.COMPONENT_MODE_REMOTE:
        config_proxy.mtimefunc = config_mtime_remote
        config_proxy.loadfunc = config_load_remote
        config_proxy.savefunc = config_save_remote
    else:
        config_proxy.mtimefunc = None
        config_proxy.loadfunc = None
        config_proxy.savefunc = None

    utils.add_type(ActionRequestedValue)
    utils.add_type(ActionValueMapping, constructor=False)
    utils.add_type(ActionTrigger, constructor=False)
    utils.add_type(Action, constructor=False)
    utils.add_type(ActionFunctionParameters)
    utils.add_type(ScheduledAction)
    utils.add_type(ActionRequestedValueParameter, constructor=False)

    utils.merge_function("get_action", f_get_action)
    utils.merge_function("run_action", f_run_action)
    utils.merge_function("schedule_action", f_schedule_action)
    utils.merge_function("cancel_scheduled_action", f_cancel_scheduled_action)
    utils.merge_function("make_function_for_action", f_make_function_for_action)
    utils.merge_function("save", f_save)
    utils.merge_function("set_action_return_value", f_set_action_return_value)
    utils.merge_function("get_current_host_url", f_get_current_host_url)
    utils.merge_function("get_remote_host_url", f_get_remote_host_url)
    builtins.trait_Iterable.merge_function(f_iterate_over)
    builtins.trait_Appendable.merge_function(f_append)

    actions.script_runner.add_script_end_cb(scriptend_save_config)

    builtins.activate()
    oti.activate()
    tti.activate()

    for activation_handler in activation_handlers.values():
        activation_handler()

def deactivate():
    utils.remove_type(ActionRequestedValue)
    utils.remove_type(ActionValueMapping)
    utils.remove_type(ActionTrigger)
    utils.remove_type(Action)
    utils.remove_type(ActionFunctionParameters)
    utils.remove_type(ScheduledAction)

    utils.remove_function("get_action", f_get_action)
    utils.remove_function("run_action", f_run_action)
    utils.remove_function("schedule_action", f_schedule_action)
    utils.remove_function("cancel_scheduled_action", f_cancel_scheduled_action)
    utils.remove_function("make_function_for_action", f_make_function_for_action)
    utils.remove_function("save", f_save)
    utils.remove_function("set_action_return_value", f_set_action_return_value)
    utils.remove_function("get_current_host_url", f_get_current_host_url)
    utils.remove_function("get_remote_host_url", f_get_remote_host_url)
    utils.remove_function("iterate_over", f_iterate_over)
    utils.remove_function("append", f_append)

    actions.script_runner.remove_script_end_cb(scriptend_save_config)

    builtins.deactivate()
    oti.deactivate()
    tti.deactivate()

    for deactivation_handler in deactivation_handlers.values():
        deactivation_handler()