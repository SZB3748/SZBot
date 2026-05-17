import actions
import config
from overlays import tronix_integrations as oti
import plugins
import requests
from tronix import json_proxy, script, script_builtins as builtins, utils
import twitch.tronix_integrations as tti
from typing import Callable

_remote_addr = None
_remote_secure = None

s = requests.Session()

activation_handlers:dict[str, Callable[[], None]] = {}
deactivation_handlers:dict[str, Callable[[], None]] = {}

def config_mtime_remote():
    r = s.head(f"http{"s"*_remote_secure}://{_remote_addr}/api/config")
    r.raise_for_status()
    return int(r.headers["MTIME"])

def config_load_remote():
    r = s.get(f"http{"s"*_remote_secure}://{_remote_addr}/api/config")
    r.raise_for_status()
    return r.json()

def config_save_remote(data):
    r = s.put(f"http{"s"*_remote_secure}://{_remote_addr}/api/config", json=data)
    return r.ok

def scriptend_save_config(s:script.Script):
    config_proxy.merge_changes()

config_proxy = json_proxy.JsonProxyRoot(config.CONFIG_FILE)


f_run_action = utils.ScriptFunction()

@f_run_action.overload(("action_name", builtins.String), ("scope", [builtins.Map, builtins.NullType], None))
async def run_action(action_name:script.ScriptVariable[str], scope:script.ScriptVariable[dict|None]):
    table = actions.load_action_table()
    action = table.get(action_name.get().inner, None)
    if action is None:
        ... #TODO error action with given name does not exist
    
    passed_scope = {}
    scope_inner = scope.get().inner
    if scope_inner is not None:
        for k,v in scope_inner.items():
            if not isinstance(k, str):
                ... #TODO error scope keys must all be strings
            passed_scope[k] = v

    s = script.Script(action.script, action.collect_script_values(passed_scope)) #TODO catch errors and re-raise with messages that make more sense to users from the in-script perspective
    if action.script_environment is None or actions.match_environment_name(action.script_environment, actions.current_environment_name):
        await actions.script_runner.run_async(s) #TODO get current script runner (somehow)
    else:
        uid, *_ = actions.enqueue_script(s, action.script_environment)
        await actions.wait_script_finish_async(uid)




def activate(api_mode:str, remote:str|None=None, secure:bool=False):
    global _remote_addr, _remote_secure

    if api_mode == plugins.COMPONENT_MODE_REMOTE:
        _remote_addr = remote
        _remote_secure = secure
        config_proxy.mtimefunc = config_mtime_remote
        config_proxy.loadfunc = config_load_remote
        config_proxy.savefunc = config_save_remote
    else:
        config_proxy.mtimefunc = None
        config_proxy.loadfunc = None
        config_proxy.savefunc = None

    
    actions.script_runner.add_script_end_cb(scriptend_save_config)
    oti.activate()
    tti.activate()

    for activation_handler in activation_handlers.values():
        activation_handler()