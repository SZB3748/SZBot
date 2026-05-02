import actions
import re
from tronix import script
import twitchio
from typing import Callable

CONDITION_TYPE_PREFIX = "prefix"
CONDITION_TYPE_SUFFIX = "suffix"
CONDITION_TYPE_CONTAINS = "contains"
CONDITION_TYPE_REGEX = "regex"
CONDITION_TYPE_USER_ID = "user_id"
CONDITION_TYPE_USER_NAME = "user_name"
CONDITION_TYPE_CHANNEL_ID = "channel_id"
CONDITION_TYPE_CHANNEL_NAME = "channel_name"

CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChatMessage], bool]] = {
    CONDITION_TYPE_PREFIX: lambda value, msg: msg.text.startswith(value),
    CONDITION_TYPE_SUFFIX: lambda value, msg: msg.text.endswith(value),
    CONDITION_TYPE_CONTAINS: lambda value, msg: value in msg.text,
    CONDITION_TYPE_REGEX: lambda value, msg: re.match(value, msg.text),
    CONDITION_TYPE_USER_ID: lambda value, msg: value == str(msg.chatter.id),
    CONDITION_TYPE_USER_NAME: lambda value, msg: value.lower() == msg.chatter.name.lower(),
    CONDITION_TYPE_CHANNEL_ID: lambda value, msg: value == str(msg.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, msg: value.lower() == msg.broadcaster.name.lower()
}

class MessageCondition:
    def __init__(self, type:str, value:str):
        self.type = type
        self.value = value

    def __getitem__(self):
        return {
            "type": self.type,
            "value": self.value
        }
    
    def __setitem__(self, d:dict[str]):
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
    
    def handle(self, msg:twitchio.ChatMessage):
        raise NotImplementedError

class ActionMessageTrigger(MessageTrigger):
    def __init__(self, name:str, conditions:list[MessageCondition], action_name:str, action_mapping:MessageActionValueMapping):
        super().__init__(name, conditions)
        self.action_name = action_name
        self.action_mapping = action_mapping
    
    def __getstate__(self):
        ...

    def __setstate__(self, d:dict[str]):
        ...
    
    def handle(self, msg:twitchio.ChatMessage):
        action = actions.load_action_table().get(self.action_name, None)


        filled = self.action_mapping.fill_values(msg)
        script_scope = action.collect_script_values(filled)
        s = script.Script(action.script, script_scope)

        if action.script_environment is None or actions.match_environment_name(action.script_environment, actions.current_environment_name):
            script_scope.setdefault