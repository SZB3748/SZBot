from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"

ONLINE_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.StreamOnline], bool]] = {
    CONDITION_TYPE_NONE: lambda value, online: True
}

OFFLINE_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.StreamOffline], bool]] = {
    CONDITION_TYPE_NONE: lambda value, offline: True
}

OnlineTrigger = event_triggers.EventTrigger[twitchio.StreamOnline]

class ActionOnlineTrigger(event_triggers.ActionEventTrigger[twitchio.StreamOnline]):
    TYPE_NAME = "twitch_online"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, online=event)

class CallbackOnlineTrigger(event_triggers.CallbackEventTrigger[twitchio.StreamOnline]):
    pass

OfflineTrigger = event_triggers.EventTrigger[twitchio.StreamOffline]

class ActionOfflineTrigger(event_triggers.ActionEventTrigger[twitchio.StreamOffline]):
    TYPE_NAME = "twitch_offline"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, offline=event)

class CallbackOfflineTrigger(event_triggers.CallbackEventTrigger[twitchio.StreamOffline]):
    pass

callback_online_triggers:dict[str, CallbackOnlineTrigger] = {}
callback_offline_triggers:dict[str, CallbackOfflineTrigger] = {}

merge_online_triggers = actions.create_triggers_merge_function(OnlineTrigger, ActionOnlineTrigger, callback_online_triggers)
merge_offline_triggers = actions.create_triggers_merge_function(OfflineTrigger, ActionOfflineTrigger, callback_offline_triggers)
