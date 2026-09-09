from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"

BEGIN_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelPredictionBegin], bool]] = {
    CONDITION_TYPE_NONE: lambda value, begin: True
}

PROGRESS_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelPredictionProgress], bool]] = {
    CONDITION_TYPE_NONE: lambda value, progress: True
}

LOCK_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelPredictionLock], bool]] = {
    CONDITION_TYPE_NONE: lambda value, lock: True
}

END_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelPredictionEnd], bool]] = {
    CONDITION_TYPE_NONE: lambda value, end: True
}

PredictionBeginTrigger = event_triggers.EventTrigger[twitchio.ChannelPredictionBegin]

class ActionPredictionBeginTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelPredictionBegin]):
    TYPE_NAME = "twitch_prediction_begin"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, prediction_begin=event)
    
class CallbackPredictionBeginTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelPredictionBegin]):
    pass

PredictionProgressTrigger = event_triggers.EventTrigger[twitchio.ChannelPredictionProgress]

class ActionPredictionProgressTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelPredictionProgress]):
    TYPE_NAME = "twitch_prediction_progress"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, prediction_progress=event)
    
class CallbackPredictionProgressTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelPredictionProgress]):
    pass

PredictionLockTrigger = event_triggers.EventTrigger[twitchio.ChannelPredictionLock]

class ActionPredictionLockTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelPredictionLock]):
    TYPE_NAME = "twitch_prediction_lock"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, prediction_lock=event)
    
class CallbackPredictionLockTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelPredictionLock]):
    pass

PredictionEndTrigger = event_triggers.EventTrigger[twitchio.ChannelPredictionEnd]

class ActionPredictionEndTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelPredictionEnd]):
    TYPE_NAME = "twitch_prediction_end"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, prediction_end=event)
    
class CallbackPredictionEndTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelPredictionEnd]):
    pass

callback_prediction_begin_triggers:dict[str, CallbackPredictionBeginTrigger] = {}
callback_prediction_progress_triggers:dict[str, CallbackPredictionProgressTrigger] = {}
callback_prediction_lock_triggers:dict[str, CallbackPredictionLockTrigger] = {}
callback_prediction_end_triggers:dict[str, CallbackPredictionEndTrigger] = {}

merge_prediction_begin_triggers = actions.create_triggers_merge_function(PredictionBeginTrigger, ActionPredictionBeginTrigger, callback_prediction_begin_triggers)
merge_prediction_progress_triggers = actions.create_triggers_merge_function(PredictionProgressTrigger, ActionPredictionProgressTrigger, callback_prediction_progress_triggers)
merge_prediction_lock_triggers = actions.create_triggers_merge_function(PredictionLockTrigger, ActionPredictionLockTrigger, callback_prediction_lock_triggers)
merge_prediction_end_triggers = actions.create_triggers_merge_function(PredictionEndTrigger, ActionPredictionEndTrigger, callback_prediction_end_triggers)
