from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"

HOLD_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.AutomodMessageHold], bool]] = {
    CONDITION_TYPE_NONE: lambda value, hold: True
}

UPDATE_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.AutomodMessageUpdate], bool]] = {
    CONDITION_TYPE_NONE: lambda value, update: True
}

AutomodHoldTrigger = event_triggers.EventTrigger[twitchio.AutomodMessageHold]

class ActionAutomodHoldTrigger(event_triggers.ActionEventTrigger[twitchio.AutomodMessageHold]):
    TYPE_NAME = "twitch_automod_hold"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, automod_hold=event)

class CallbackAutomodHoldTrigger(event_triggers.ActionEventTrigger[twitchio.AutomodMessageHold]):
    pass

AutomodUpdateTrigger = event_triggers.EventTrigger[twitchio.AutomodMessageUpdate]

class ActionAutomodUpdateTrigger(event_triggers.ActionEventTrigger[twitchio.AutomodMessageUpdate]):
    TYPE_NAME = "twitch_automod_update"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, automod_update=event)

class CallbackAutomodUpdateTrigger(event_triggers.ActionEventTrigger[twitchio.AutomodMessageUpdate]):
    pass

callback_automod_hold_triggers:dict[str, CallbackAutomodHoldTrigger] = {}
callback_automod_update_triggers:dict[str, CallbackAutomodUpdateTrigger] = {}

merge_automod_hold_triggers = actions.create_triggers_merge_function(AutomodHoldTrigger, ActionAutomodHoldTrigger, callback_automod_hold_triggers)
merge_automod_update_triggers = actions.create_triggers_merge_function(AutomodUpdateTrigger, ActionAutomodUpdateTrigger, callback_automod_update_triggers)
