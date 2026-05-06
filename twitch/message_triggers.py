from . import tronix_integrations as tti
import actions
import datafile
import json
import os
import re
from tronix import script
import twitchio
from twitchio.ext import commands
from typing import Any, Callable

CONDITION_TYPE_NONE = "none"
CONDITION_TYPE_PREFIX = "prefix"
CONDITION_TYPE_SUFFIX = "suffix"
CONDITION_TYPE_CONTAINS = "contains"
CONDITION_TYPE_REGEX = "regex"
CONDITION_TYPE_USER_ID = "user_id"
CONDITION_TYPE_USER_NAME = "user_name"
CONDITION_TYPE_CHANNEL_ID = "channel_id"
CONDITION_TYPE_CHANNEL_NAME = "channel_name"

MESSAGE_TRIGGERS_PATH = datafile.makepath("message_triggers.json")

CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChatMessage], bool]] = {
    CONDITION_TYPE_NONE: lambda value, msg: True,
    CONDITION_TYPE_PREFIX: lambda value, msg: msg.text.startswith(value),
    CONDITION_TYPE_SUFFIX: lambda value, msg: msg.text.endswith(value),
    CONDITION_TYPE_CONTAINS: lambda value, msg: value in msg.text,
    CONDITION_TYPE_REGEX: lambda value, msg: re.match(value, msg.text),
    CONDITION_TYPE_USER_ID: lambda value, msg: value == str(msg.chatter.id),
    CONDITION_TYPE_USER_NAME: lambda value, msg: value.lower() == msg.chatter.name.lower(),
    CONDITION_TYPE_CHANNEL_ID: lambda value, msg: value == str(msg.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, msg: value.lower() == msg.broadcaster.name.lower()
}

MessageTriggerCallback = Callable[[commands.Bot, twitchio.ChatMessage], Any]

class MessageCondition:
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
    
    def match(self, msg:twitchio.ChatMessage):
        matcher = CONDITION_MATCHERS[self.type]
        return matcher(self.value, msg)


class MessageActionValueMapping(actions.ActionValueMapping):
    def __init__(self, message_name:str, extra_data:dict[str]):
        self.message_name = message_name
        self.extra_data = extra_data

    def fill_values(self, msg:twitchio.ChatMessage):
        d = self.extra_data.copy()
        if self.message_name:
            d.setdefault(self.message_name, msg)
        return d
    
    def __getstate__(self):
        return {
            "message_name": self.message_name,
            "extra_data": actions.extra_data_serialize(self.extra_data)
        }
    
    def __setstate__(self, d:dict[str]):
        self.message_name:str = str(d["message_name"])
        self.extra_data:dict[str] = actions.extra_data_deserialize(d["extra_data"])

class MessageTrigger(actions.Trigger):
    def __init__(self, name:str, conditions:list[MessageCondition]):
        self.name = name
        self.conditions = conditions

    def match(self, msg:twitchio.ChatMessage):
        return all(c.match(msg) for c in self.conditions)
    
    def handle(self, bot:commands.Bot, msg:twitchio.ChatMessage):
        raise NotImplementedError

class ActionMessageTrigger(MessageTrigger):
    def __init__(self, name:str, conditions:list[MessageCondition], action_name:str, action_mapping:MessageActionValueMapping):
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
        action_mapping = MessageActionValueMapping.__new__(MessageActionValueMapping)
        action_mapping.__setstate__(d["action_mapping"])
        self.conditions = []
        conditions = d["conditions"]
        if isinstance(conditions, list):
            for cd in conditions:
                condition = MessageCondition.__new__(MessageCondition)
                condition.__setstate__(cd)
                self.conditions.append(condition)
        self.action_mapping = action_mapping
    
    def handle(self, bot:commands.Bot, msg:twitchio.ChatMessage):
        action = actions.load_action_table().get(self.action_name, None)

        filled = self.action_mapping.fill_values(msg)
        script_scope = action.collect_script_values(filled)
        s = script.Script(action.script, script_scope)

        if action.script_environment is None or actions.match_environment_name(action.script_environment, actions.current_environment_name):
            script_scope.setdefault(tti.TWITCH_CONTEXT_VAR_NAME, script.ScriptVariable(script.wrap_python_value(tti.BotScriptContext(bot, message=msg))))
            return actions.script_runner.run_async(s)
        else:
            uid, *_ = actions.enqueue_script(s, action.script_environment)
            async def _wait():
                await actions.wait_script_finish_async(uid)
            return _wait()
        
class CallbackMessageTrigger(MessageTrigger):
    @staticmethod
    def create(name:str, *conditions:MessageCondition):
        def decor(callback:MessageTriggerCallback):
            return CallbackMessageTrigger(name, list(conditions), callback)
        return decor

    @staticmethod
    def new(name:str, conditions:list[MessageCondition], callback:MessageTriggerCallback):
        return CallbackMessageTrigger(name, conditions, callback)

    def __init__(self, name:str, conditions:list[MessageCondition], callback:MessageTriggerCallback, bind=None):
        super().__init__(name, conditions)
        self.callback = callback
        self.bind = bind

    def handle(self, bot:commands.Bot, msg:twitchio.ChatMessage):
        if self.bind is None:
            cb = self.callback
        else:
            cb = self.callback.__get__(self.bind, type(self.bind))
        return cb(bot, msg)

    def __call__(self, bot:commands.Bot, msg:twitchio.ChatMessage):
        return self.handle(bot, msg)
    
callback_message_triggers:dict[str, CallbackMessageTrigger] = {}

def load_message_triggers(path:str=None)->dict[str, ActionMessageTrigger]:
    if path is None:
        path = MESSAGE_TRIGGERS_PATH
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        d:dict[str,dict[str]] = json.load(f)
    rtv = {}
    for k,v in d.items():
        rtv[k] = cmd = ActionMessageTrigger.__new__(ActionMessageTrigger)
        cmd.__setstate__(v)
    return rtv

def save_message_triggers(commands:dict[str, ActionMessageTrigger], path:str=None):
    c = json.dumps({c.name:c.__getstate__() for c in commands.values() if isinstance(c, ActionMessageTrigger)}, indent=4)
    with open(MESSAGE_TRIGGERS_PATH if path is None else path, "w") as f:
        f.write(c)

def merge_message_triggers(path:str=None)->dict[str,MessageTrigger]:
    d = callback_message_triggers.copy()
    d.update(load_message_triggers(path))
    return d