import actions
import config
from overlays import tronix_integrations as oti
import plugins
import requests
import runtime as rt
from tronix import json_proxy, script, script_builtins as builtins, utils
import twitch.tronix_integrations as tti
from typing import Any, Callable


s = requests.Session()

activation_handlers:dict[str, Callable[[], None]] = {}
deactivation_handlers:dict[str, Callable[[], None]] = {}

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
    r = s.head(f"http{"s"*rt.remote_secure}://{rt.remote_addr[0]}:{rt.remote_addr[1]}/api/config")
    r.raise_for_status()
    return int(r.headers["MTIME"])

def config_load_remote():
    r = s.get(f"http{"s"*rt.remote_secure}://{rt.remote_addr[0]}:{rt.remote_addr[1]}/api/config")
    r.raise_for_status()
    return r.json()

def config_save_remote(data):
    r = s.put(f"http{"s"*rt.remote_secure}://{rt.remote_addr[0]}:{rt.remote_addr[1]}/api/config", json=data)
    return r.ok

def scriptend_save_config(s:script.Script):
    config_proxy.merge_changes()

config_proxy = json_proxy.JsonProxyRoot(config.CONFIG_FILE)

ActionRequestedValue = _ActionRequestedValueType("ActionRequestedValue", actions.ActionRequestedValue, builtins.BASE_TYPE)
ActionValueMapping = _ActionValueMappingType("ActionValueMapping", actions.ActionValueMapping, builtins.BASE_TYPE)
ActionTrigger = _ActionTriggerType("ActionTrigger", actions.Trigger, builtins.BASE_TYPE)
Action = _ActionType("Action", actions.Action, builtins.BASE_TYPE)

f_get_action = utils.ScriptFunction()
f_run_action = utils.ScriptFunction()
f_set_action_return_value = utils.ScriptFunction()
f_save = utils.ScriptFunction()

@f_get_action.overload(("name", builtins.String))
async def get_action(name:script.ScriptVariable[str]):
    table = actions.load_action_table()
    return script.wrap_python_value(table.get(name.get().inner, None))

@f_run_action.overload(("action", [Action, builtins.String]), ("scope", [builtins.Map, builtins.NullType], None))
async def run_action(action:script.ScriptVariable[actions.Action|str], scope:script.ScriptVariable[dict|None]):
    table = actions.load_action_table()
    av = action.get()
    if av.type.issubtype(Action):
        assert isinstance(av.inner, actions.Action)
        a = av.inner
    else:
        assert isinstance(av.inner, str)
        a = table.get(av.inner, None)
        if a is None:
            ... #TODO error action with given name does not exist
    
    passed_scope = {}
    scope_inner = scope.get().inner
    if scope_inner is not None:
        for k,v in scope_inner.items():
            if not isinstance(k, str):
                ... #TODO error scope keys must all be strings
            passed_scope[k] = v

    s = script.Script(a.script, a.collect_script_values(passed_scope)) #TODO catch errors and re-raise with messages that make more sense to users from the in-script perspective
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

@f_set_action_return_value.overload(("value", builtins.AnyType), pass_ctx=True)
async def set_action_return_value(ctx:script.ScriptContext, value:script.ScriptVariable):
    ns = ctx.stack.find_name(actions.ACTION_RETURN_VALUE_VAR_NAME)
    if ns is None or ns is ctx.script.scope:
        ctx.script.scope[actions.ACTION_RETURN_VALUE_VAR_NAME] = script.ScriptVariable(value.get())
    else:
        ctx.script.scope[actions.ACTION_RETURN_VALUE_VAR_NAME] = ns.pop(actions.ACTION_RETURN_VALUE_VAR_NAME)

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

    utils.merge_function("get_action", f_get_action)
    utils.merge_function("run_action", f_run_action)
    utils.merge_function("save", f_save)
    utils.merge_function("set_action_return_value", f_set_action_return_value)

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

    utils.remove_function("get_action", f_get_action)
    utils.remove_function("run_action", f_run_action)
    utils.remove_function("save", f_save)
    utils.remove_function("set_action_return_value", f_set_action_return_value)

    actions.script_runner.remove_script_end_cb(scriptend_save_config)

    builtins.deactivate()
    oti.deactivate()
    tti.deactivate()

    for deactivation_handler in deactivation_handlers.values():
        deactivation_handler()