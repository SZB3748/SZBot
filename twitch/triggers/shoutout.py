from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"

CREATE_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ShoutoutCreate], bool]] = {
    CONDITION_TYPE_NONE: lambda value, create: True
}

RECEIVE_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ShoutoutReceive], bool]] = {
    CONDITION_TYPE_NONE: lambda value, receive: True
}

ShoutoutCreateTrigger = event_triggers.EventTrigger[twitchio.ShoutoutCreate]

class ActionShoutoutCreateTrigger(event_triggers.ActionEventTrigger[twitchio.ShoutoutCreate]):
    TYPE_NAME = "twitch_shoutout_create"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, shoutout_create=event)

class CallbackShoutoutCreateTrigger(event_triggers.CallbackEventTrigger[twitchio.ShoutoutCreate]):
    pass

ShoutoutReceiveTrigger = event_triggers.EventTrigger[twitchio.ShoutoutReceive]

class ActionShoutoutReceiveTrigger(event_triggers.ActionEventTrigger[twitchio.ShoutoutReceive]):
    TYPE_NAME = "twitch_shoutout_receive"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, shoutout_receive=event)

class CallbackShoutoutReceiveTrigger(event_triggers.CallbackEventTrigger[twitchio.ShoutoutReceive]):
    pass

callback_shoutout_create_triggers:dict[str, CallbackShoutoutCreateTrigger] = {}
callback_shoutout_receive_triggers:dict[str, CallbackShoutoutReceiveTrigger] = {}

merge_shoutout_create_triggers = actions.create_triggers_merge_function(ShoutoutCreateTrigger, ActionShoutoutCreateTrigger, callback_shoutout_create_triggers)
merge_shoutout_receive_triggers = actions.create_triggers_merge_function(ShoutoutReceiveTrigger, ActionShoutoutReceiveTrigger, callback_shoutout_receive_triggers)
