from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"

CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelAdBreakBegin], bool]] = {
    CONDITION_TYPE_NONE: lambda value, ad_begin: True,
}

AdBeginTrigger = event_triggers.EventTrigger[twitchio.ChannelAdBreakBegin]

class ActionAdBeginTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelAdBreakBegin]):
    TYPE_NAME = "twitch_ad_begin"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, ad_begin=event)

class CallbackAdBeginTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelAdBreakBegin]):
    pass

callback_ad_begin_triggers:dict[str, CallbackAdBeginTrigger] = {}

merge_ad_begin_triggers = actions.create_triggers_merge_function(AdBeginTrigger, ActionAdBeginTrigger, callback_ad_begin_triggers)
