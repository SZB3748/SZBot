from . import event_triggers, tronix_integrations as tti
import actions
import re
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"
CONDITION_TYPE_BITS_GREATER_THAN = "bits_gt"
CONDITION_TYPE_BITS_LESS_THAN = "bits_lt"
CONDITION_TYPE_BITS_EQUAL = "bits_eq"
CONDITION_TYPE_BITS_NOT_EQUAL = "bits_ne"
CONDITION_TYPE_USER_ID = "user_id"
CONDITION_TYPE_USER_NAME = "user_name"
CONDITION_TYPE_CHANNEL_ID = "channel_id"
CONDITION_TYPE_CHANNEL_NAME = "channel_name"
CONDITION_TYPE_IS_ANONYMOUS = "is_anonymous"
CONDITION_TYPE_MSG_PREFIX = "msg_prefix"
CONDITION_TYPE_MSG_SUFFIX = "msg_suffix"
CONDITION_TYPE_MSG_CONTAINS = "msg_contains"
CONDITION_TYPE_MSG_REGEX = "msg_regex"

CHEER_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelCheer], bool]] = {
    CONDITION_TYPE_NONE: lambda value, cheer: True,
    CONDITION_TYPE_BITS_GREATER_THAN: lambda value, cheer: cheer.bits > int(value),
    CONDITION_TYPE_BITS_LESS_THAN: lambda value, cheer: cheer.bits < int(value),
    CONDITION_TYPE_BITS_EQUAL: lambda value, cheer: cheer.bits == int(value),
    CONDITION_TYPE_BITS_NOT_EQUAL: lambda value, cheer: cheer.bits != int(value),
    CONDITION_TYPE_USER_ID: lambda value, cheer: not cheer.anonymous and value == str(cheer.user.id),
    CONDITION_TYPE_USER_NAME: lambda value, cheer: not cheer.anonymous and value.lower() == cheer.user.name.lower(),
    CONDITION_TYPE_CHANNEL_ID: lambda value, cheer: value == str(cheer.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, cheer: value.lower() == cheer.broadcaster.name.lower(),
    CONDITION_TYPE_IS_ANONYMOUS: lambda value, cheer: value.lower() == str(cheer.anonymous).lower(),
    CONDITION_TYPE_MSG_PREFIX: lambda value, cheer: cheer.message.startswith(value),
    CONDITION_TYPE_MSG_SUFFIX: lambda value, cheer: cheer.message.endswith(value),
    CONDITION_TYPE_MSG_CONTAINS: lambda value, cheer: value in cheer.message,
    CONDITION_TYPE_MSG_REGEX: lambda value, cheer: re.match(value, cheer.message),
}

BITSUSE_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelBitsUse], bool]] = {
    CONDITION_TYPE_NONE: lambda value, bitsuse: True,
    CONDITION_TYPE_BITS_GREATER_THAN: lambda value, bitsuse: int(value) > bitsuse.bits,
    CONDITION_TYPE_BITS_LESS_THAN: lambda value, bitsuse: int(value) < bitsuse.bits,
    CONDITION_TYPE_BITS_EQUAL: lambda value, bitsuse: int(value) == bitsuse.bits,
    CONDITION_TYPE_BITS_NOT_EQUAL: lambda value, bitsuse: int(value) != bitsuse.bits,
    CONDITION_TYPE_USER_ID: lambda value, bitsuse: value == str(bitsuse.user.id),
    CONDITION_TYPE_USER_NAME: lambda value, bitsuse: value.lower() == bitsuse.user.name.lower(),
    CONDITION_TYPE_CHANNEL_ID: lambda value, bitsuse: value == str(bitsuse.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, bitsuse: value.lower() == bitsuse.broadcaster.name.lower(),
    #CONDITION_TYPE_IS_ANONYMOUS: lambda value, bitsuse: value.lower() == str(bitsuse.anonymous).lower() #anonymous condition is not applicable
    CONDITION_TYPE_MSG_PREFIX: lambda value, bitsuse: (bitsuse.text or "").startswith(value),
    CONDITION_TYPE_MSG_SUFFIX: lambda value, bitsuse: (bitsuse.text or "").endswith(value),
    CONDITION_TYPE_MSG_CONTAINS: lambda value, bitsuse: value in (bitsuse.text or ""),
    CONDITION_TYPE_MSG_REGEX: lambda value, bitsuse: re.match(value, (bitsuse.text or "")),
}

CheerTrigger = event_triggers.EventTrigger[twitchio.ChannelCheer]
BitsUseTrigger = event_triggers.EventTrigger[twitchio.ChannelBitsUse]

class ActionCheerTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelCheer]):
    TYPE_NAME = "twitch_cheer"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, cheer=event)

class CallbackCheerTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelCheer]):
    pass

class ActionBitsUseTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelBitsUse]):
    TYPE_NAME = "twitch_bitsuse"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, bitsuse=event)
    
class CallbackCheerTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelBitsUse]):
    pass

callback_cheer_triggers:dict[str, CallbackCheerTrigger] = {}
callback_bitsuse_triggers:dict[str, CallbackCheerTrigger] = {}

merge_cheer_triggers = actions.create_triggers_merge_function(CheerTrigger, ActionCheerTrigger, callback_cheer_triggers)
merge_bitsuse_triggers = actions.create_triggers_merge_function(BitsUseTrigger, ActionBitsUseTrigger, callback_bitsuse_triggers)