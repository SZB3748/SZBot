from . import keybind
import actions
from tronix import script
from typing import Any, Callable

KeyBindTriggerCallback = Callable[[list[keybind.KeyBind], keybind.KeyBind], Any]

class KeyBindActionValueMapping(actions.ActionValueMapping):
    def __init__(self, trigger_name:str, keybinds_name:str, match_name:str, extra_data:dict[str]):
        self.trigger_name = trigger_name
        self.keybinds_name = keybinds_name
        self.match_name = match_name
        self.extra_data = extra_data

    def fill_values(self, trigger:"KeyBindTrigger", kb:keybind.KeyBind):
        d = self.extra_data.copy()
        if self.keybinds_name:
            d[self.keybinds_name] = trigger.kbs
        if self.match_name:
            d[self.match_name] = kb
        return d

    def __getstate__(self)->dict[str]:
        return {
            "keybinds_name": self.keybinds_name,
            "match_name": self.match_name,
            "extra_data": actions.extra_data_serialize(self.extra_data)
        }
    
    def __setstate__(self, d:dict[str]):
        self.keybinds_name = str(d["keybinds_name"])
        self.match_name = str(d["match_name"])
        self.extra_data:dict[str] = actions.extra_data_deserialize(d["extra_data"])


class KeyBindTrigger(actions.Trigger):
    def __init__(self, name:str, kbs:list[keybind.KeyBind]):
        super().__init__(name)
        self.kbs = kbs

    def handle(self):
        raise NotImplementedError

class ActionKeyBindTrigger(KeyBindTrigger):

    TYPE_NAME = "keybind"

    def __init__(self, name:str, kbs:list[keybind.KeyBind], action_name:str, action_mapping:KeyBindActionValueMapping):
        super().__init__(name, kbs)
        self.action_name = action_name
        self.action_mapping = action_mapping

    async def handle(self, kb:keybind.KeyBind):
        action = actions.load_action_table().get(self.action_name, None)
        if action is None:
            raise actions.ActionNotFound(f"Could not find action: {self.action_name}", action_name=self.action_name)
        script_scope = {}
        if self.action_mapping is not None:
            filled_values = self.action_mapping.fill_values(self, kb)
            script_scope.update(action.collect_script_values(filled_values))
        s = script.Script(action.script, script_scope)
        if action.is_script_environment_local():
            await actions.script_runner.run_async(s)
            rtvar = s.scope.get(actions.ACTION_RETURN_VALUE_VAR_NAME, None)
            if isinstance(rtvar, script.ScriptVariable):
                return rtvar.get()
        else:
            uid, *_ = actions.enqueue_script(s, action.script_environment)
            success, return_value = await actions.wait_script_finish_async(uid)
            if success:
                if return_value is not None:
                    s.scope[actions.ACTION_RETURN_VALUE_VAR_NAME] = script.ScriptVariable(return_value)
                return return_value

    def __getstate__(self)->dict[str]:
        return {
            "name": self.name,
            "keybinds":[dict(keys=kb.keys, mode=kb.mode.name) for kb in self.kbs],
            "action_name": self.action_name,
            "action_mapping": self.action_mapping.__getstate__()
        }
    
    def __setstate__(self, d:dict[str]):
        kbs_d = d["keybinds"]
        action_mapping = KeyBindActionValueMapping.__new__(KeyBindActionValueMapping)
        action_mapping.__setstate__(d["action_mapping"])
        self.name = str(d["name"])
        kbs:list[keybind.KeyBind] = []
        for kbd in kbs_d:
            if isinstance(kbd, dict):
                kbs.append(keybind.KeyBind(kbd["keys"], keybind.KeyBindMode(kbd["mode"])))
        self.kbs = kbs
        self.action_name = str(d["action_name"])
        self.action_mapping = action_mapping

class CallbackKeyBindTrigger(KeyBindTrigger):
    @staticmethod
    def create(*kbs:keybind.KeyBind, name:str|None=None):
        assert kbs, "Must list at least one keybind."
        def decor(callback:KeyBindTriggerCallback):
            return CallbackKeyBindTrigger(
                callback.__name__ if name is None else name,
                list(kbs),
                callback
            )
        return decor
        
    @staticmethod
    def new(callback:KeyBindTriggerCallback, kbs:list[keybind.KeyBind], name:str|None=None):
        assert kbs, "Must list at least one keybind."
        return CallbackKeyBindTrigger(
            callback.__name__ if name is None else name,
            kbs,
            callback
        )
    
    def __init__(self, name:str, kbs:list[keybind.KeyBind], callback:KeyBindTriggerCallback, bind=None):
        super().__init__(name, kbs)
        self.callback = callback
        self.bind = bind

    def handle(self, kb:keybind.KeyBind):
        if self.bind is None:
            cb = self.callback
        else:
            cb = self.callback.__get__(self.bind, type(self.bind))
        return cb(self.kbs, kb)
    
    def __call__(self, kb:keybind.KeyBind):
        self.handle(kb)

callback_keybind_triggers:dict[str, CallbackKeyBindTrigger] = {}

merge_keybind_triggers = actions.create_triggers_merge_function(KeyBindTrigger, ActionKeyBindTrigger, callback_keybind_triggers)
