import actions
import config
import plugins
import requests
from tronix import json_proxy, Script
import tronix_twitch_integrations

_remote_addr = None
_remote_secure = None

s = requests.Session()

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

def scriptend_save_config(s:Script):
    config_proxy.merge_changes()

config_proxy = json_proxy.JsonProxyRoot(config.CONFIG_FILE)

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
    tronix_twitch_integrations.activate()