from . import event_triggers, tronix_integrations as tti
import datafile
import re
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"
CONDITION_TYPE_PREFIX = "prefix"
CONDITION_TYPE_SUFFIX = "suffix"
CONDITION_TYPE_CONTAINS = "contains"
CONDITION_TYPE_REGEX = "regex"
CONDITION_TYPE_USER_ID = "user_id"
CONDITION_TYPE_USER_NAME = "user_name"
CONDITION_TYPE_CHANNEL_ID = "channel_id"
CONDITION_TYPE_CHANNEL_NAME = "channel_name"
CONDITION_TYPE_LISTENED_CHANNEL_ID = "listened_channel_id"
CONDITION_TYPE_LISTENED_CHANNEL_NAME = "listened_channel_name"
CONDITION_TYPE_IS_SHARED = "is_shared"

MESSAGE_TRIGGERS_PATH = datafile.makepath("message_triggers.json")

CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChatMessage], bool]] = {
    CONDITION_TYPE_NONE: lambda value, msg: True,
    CONDITION_TYPE_PREFIX: lambda value, msg: msg.text.startswith(value),
    CONDITION_TYPE_SUFFIX: lambda value, msg: msg.text.endswith(value),
    CONDITION_TYPE_CONTAINS: lambda value, msg: value in msg.text,
    CONDITION_TYPE_REGEX: lambda value, msg: re.match(value, msg.text),
    CONDITION_TYPE_USER_ID: lambda value, msg: value == str(msg.chatter.id),
    CONDITION_TYPE_USER_NAME: lambda value, msg: value.lower() == msg.chatter.name.lower(),
    CONDITION_TYPE_CHANNEL_ID: lambda value, msg: value == str((msg.source_broadcaster or msg.broadcaster).id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, msg: value.lower() == (msg.source_broadcaster or msg.broadcaster).name.lower(),
    CONDITION_TYPE_LISTENED_CHANNEL_ID: lambda value, msg: value == str(msg.broadcaster.id),
    CONDITION_TYPE_LISTENED_CHANNEL_NAME: lambda value, msg: value.lower() == msg.broadcaster.name.lower(),
    CONDITION_TYPE_IS_SHARED: lambda value, msg: value.lower() == str(msg.source_broadcaster is None).lower()
}

MessageTrigger = event_triggers.EventTrigger[twitchio.ChatMessage]

class ActionMessageTrigger(event_triggers.ActionEventTrigger[twitchio.ChatMessage]):
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, message=event)
        
class CallbackMessageTrigger(event_triggers.CallbackEventTrigger[twitchio.ChatMessage]):
    pass


callback_message_triggers:dict[str, CallbackMessageTrigger] = {}

load_message_triggers, save_message_triggers, merge_message_triggers = event_triggers.create_file_functions(ActionMessageTrigger, callback_message_triggers, MESSAGE_TRIGGERS_PATH)
