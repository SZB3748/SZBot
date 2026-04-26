from . import keybind
import actions
import datafile
import json
import os
from tronix import script
from typing import Any, Callable

KEYBIND_TRIGGER_PATH = datafile.makepath("keybind_triggers.json")

KeyBindTriggerCallback = Callable[[str, keybind.KeyBind], Any]

class KeyBindActionValueMapping(actions.ActionValueMapping):
    def __init__(self, trigger_name:str, keybind_name:str, extra_data:dict[str]):
        self.trigger_name = trigger_name
        self.keybind_name = keybind_name
        self.extra_data = extra_data

    def fill_values(self, trigger:"KeyBindTrigger"):
        d = self.extra_data.copy()
        if self.trigger_name:
            d[self.trigger_name] = trigger.name
        if self.keybind_name:
            d[self.keybind_name] = trigger.kb
        return d

    def __getstate__(self)->dict[str]:
        return {
            "trigger_name": self.trigger_name,
            "keybind_name": self.keybind_name,
            "extra_data": self.extra_data
        }
    
    def __setstate__(self, d:dict[str]):
        self.trigger_name = str(d["trigger_name"])
        self.keybind_name = str(d["keybind_name"])
        self.extra_data:dict[str] = d["extra_data"]


class KeyBindTrigger:
    def __init__(self, name:str, kb:keybind.KeyBind):
        self.name = name
        self.kb = kb

    def handle(self):
        raise NotImplementedError

class ActionKeyBindTrigger(KeyBindTrigger):

    def __init__(self, name:str, kb:keybind.KeyBind, action_name:str, action_mapping:KeyBindActionValueMapping):
        super().__init__(name, kb)
        self.action_name = action_name
        self.action_mapping = action_mapping

    def handle(self):
        action = actions.load_action_table().get(self.action_name, None)
        if action is None:
            ... #TODO exception unknown action
        script_scope = {}
        if self.action_mapping is not None:
            filled_values = self.action_mapping.fill_values(self)
            script_scope.update(action.collect_script_values(filled_values))
        s = script.Script(action.script, script_scope)
        if action.script_environment is None or actions.match_environment_name(action.script_environment, actions.current_environment_name):
            return actions.script_runner.run_async(s)
        else:
            uid, *_ = actions.enqueue_script(s, action.script_environment)
            async def _wait():
                print(uid, "waiting")
                await actions.wait_script_finish_async(uid)
                print(uid, "done waiting")
            return _wait()

    def __getstate__(self)->dict[str]:
        return {
            "keybind": {
                "keys": self.kb.keys,
                "mode": self.kb.mode
            },
            "action_name": self.action_name,
            "action_mapping": self.action_mapping.__getstate__()
        }
    
    def __setstate__(self, d:dict[str]):
        kb = d["keybind"]
        action_mapping = KeyBindActionValueMapping.__new__(KeyBindActionValueMapping)
        action_mapping.__setstate__(d["action_mapping"])

        self.kb = keybind.KeyBind(kb["keys"], keybind.KeyBindMode(kb["mode"]))
        self.action_name = str(d["action_name"])
        self.action_mapping = action_mapping

class CallbackKeyBindTrigger(KeyBindTrigger):
    @staticmethod
    def create(keys:str, mode:keybind.KeyBindMode|str|int, name:str|None=None):
        if isinstance(mode, str):
            mode = keybind.KeyBindMode[mode]
        elif isinstance(mode, (int,float)):
            mode = keybind.KeyBindMode(int(mode))
        def decor(callback:KeyBindTriggerCallback):
            return CallbackKeyBindTrigger(
                callback.__name__ if name is None else name,
                keybind.KeyBind(keys, mode),
                callback
            )
        return decor
        
    @staticmethod
    def new(callback:KeyBindTriggerCallback, keys:str, mode:keybind.KeyBindMode|str|int, name:str|None=None):
        if isinstance(mode, str):
            mode = keybind.KeyBindMode[mode]
        elif isinstance(mode, (int,float)):
            mode = keybind.KeyBindMode(int(mode))
        return CallbackKeyBindTrigger(
            callback.__name__ if name is None else name,
            keybind.KeyBind(keys, mode),
            callback
        )
    
    def __init__(self, name:str, kb:keybind.KeyBind, callback:KeyBindTriggerCallback, bind=None):
        self.name = name
        self.kb = kb
        self.callback = callback
        self.bind = bind

    def handle(self):
        if self.bind is None:
            cb = self.callback
        else:
            cb = self.callback.__get__(self.bind, type(self.bind))
        return cb(self.name, self.kb)
    
    def __call__(self):
        self.handle()

callback_keybind_triggers:dict[str, CallbackKeyBindTrigger] = {}

def load_keybind_triggers(path:str=None)->dict[str,ActionKeyBindTrigger]:
    if path is None:
        path = KEYBIND_TRIGGER_PATH
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        d:dict[str,dict[str]] = json.load(f)
    rtv = {}
    for k,v in d.items():
        rtv[k] = kbt = ActionKeyBindTrigger.__new__(ActionKeyBindTrigger)
        kbt.__setstate__(v)
        kbt.name = k
    return rtv

def save_keybind_triggers(triggers:dict[str, ActionKeyBindTrigger], path:str=None):
    c = json.dumps({kbt.name:kbt.__getstate__() for kbt in triggers.values()}, indent=4)
    with open(KEYBIND_TRIGGER_PATH if path is None else path, "w") as f:
        f.write(c)

def merge_keybind_triggers(path:str=None)->dict[str,KeyBindTrigger]:
    d = callback_keybind_triggers.copy()
    d.update(load_keybind_triggers(path))
    return d