from . import tronix_integrations as tti
import actions
import json
import os
from tronix import script
from twitchio.ext import commands
from typing import Any, Callable

class Condition[T]:
    def __init__(self, type:str, value:str):
        self.type = type
        self.value = value

    def __getstate__(self):
        return {
            "type": self.type,
            "value": self.value
        }
    
    def __setstate__(self, d:dict[str]):
        self.type = str(d["type"])
        self.value = str(d["value"])
    
    def match(self, x:T, condition_matchers:dict[str,Callable[[str, T], bool]]):
        matcher = condition_matchers[self.type]
        return matcher(self.value, x)
    

class EventActionValueMapping[T](actions.ActionValueMapping):
    def __init__(self, event_name:str, extra_data:dict[str]):
        self.event_name = event_name
        self.extra_data = extra_data
    
    def fill_values(self, event:T):
        d = self.extra_data.copy()
        if self.event_name:
            d.setdefault(self.event_name, event)
        return d
    
    def __getstate__(self):
        return {
            "event_name": self.event_name,
            "extra_data": actions.extra_data_serialize(self.extra_data)
        }
    
    def __setstate__(self, d:dict[str]):
        self.event_name = str(d["event_name"])
        self.extra_data:dict[str] = actions.extra_data_deserialize(d["extra_data"])

class EventTrigger[T](actions.Trigger):
    def __init__(self, name:str, conditions:list[Condition[T]]):
        super().__init__(name)
        self.conditions = conditions
    
    def match(self, event:T, condition_matchers:dict[str,Callable[[str, T], bool]]):
        return all(c.match(event, condition_matchers) for c in self.conditions)

    def handle(self, bot:commands.Bot, event:T):
        raise NotImplementedError
    
class ActionEventTrigger[T](EventTrigger[T]):
    def __init__(self, name:str, conditions:list[Condition[T]], action_name:str, action_mapping:EventActionValueMapping[T]):
        super().__init__(name, conditions)
        self.action_name = action_name
        self.action_mapping = action_mapping

    def __getstate__(self):
        return {
            "name": self.name,
            "conditions": [condition.__getstate__() for condition in self.conditions],
            "action_name": self.action_name,
            "action_mapping": self.action_mapping.__getstate__()
        }
    
    def __setstate__(self, d:dict[str]):
        self.name = str(d["name"])
        self.action_name = str(d["action_name"])  
        action_mapping = EventActionValueMapping.__new__(EventActionValueMapping)
        action_mapping.__setstate__(d["action_mapping"])
        self.conditions = []
        conditions = d["conditions"]
        if isinstance(conditions, list):
            for cd in conditions:
                condition = Condition.__new__(Condition)
                condition.__setstate__(cd)
                self.conditions.append(condition)
        self.action_mapping = action_mapping

    def create_bot_script_context(self, bot:commands.Bot, event:T)->tti.BotScriptContext:
        raise NotImplementedError

    async def handle(self, bot:commands.Bot, event:T):
        action = actions.load_action_table().get(self.action_name, None)
        if action is None:
            ... #TODO exception action not found

        filled = self.action_mapping.fill_values(event)
        script_scope = action.collect_script_values(filled)
        s = script.Script(action.script, script_scope)

        if action.is_script_environment_local():
            script_scope.setdefault(tti.TWITCH_CONTEXT_VAR_NAME, script.ScriptVariable(script.wrap_python_value(self.create_bot_script_context(bot, event))))
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
        
class CallbackEventTrigger[T](EventTrigger[T]):

    @classmethod
    def create(cls, name:str, *conditions:Condition|tuple[str, str]):
        def decor(callback:Callable[[commands.Bot, T], Any]):
            return cls(name, [c if isinstance(c, Condition) else Condition(*c) for c in conditions], callback)
        return decor

    @classmethod
    def new(cls, name:str, conditions:list[Condition], callback:Callable[[commands.Bot, T], Any]):
        return cls(name, conditions, callback)

    def __init__(self, name:str, conditions:list[Condition], callback:Callable[[commands.Bot, T], Any], bind=None):
        super().__init__(name, conditions)
        self.callback = callback
        self.bind = bind

    def handle(self, bot:commands.Bot, event:T):
        if self.bind is None:
            cb = self.callback
        else:
            cb = self.callback.__get__(self.bind, type(self.bind))
        return cb(bot, event)

    def __call__(self, bot:commands.Bot, event:T):
        return self.handle(bot, event)
