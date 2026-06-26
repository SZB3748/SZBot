from . import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"
CONDITION_TYPE_CHANNEL_ID = "channel_id"
CONDITION_TYPE_CHANNEL_NAME = "channel_name"
CONDITION_TYPE_LEVEL_GREATER_THAN = "level_gt"
CONDITION_TYPE_LEVEL_LESS_THAN = "level_lt"
CONDITION_TYPE_LEVEL_EQUAL = "level_eq"
CONDITION_TYPE_LEVEL_NOT_EQUAL = "level_ne"
CONDITION_TYPE_TOTAL_GREATER_THAN = "total_gt"
CONDITION_TYPE_TOTAL_LESS_THAN = "total_lt"
CONDITION_TYPE_TOTAL_EQUAL = "total_eq"
CONDITION_TYPE_TOTAL_NOT_EQUAL = "total_ne"
CONDITION_TYPE_PROGRESS_GREATER_THAN = "progress_gt"
CONDITION_TYPE_PROGRESS_LESS_THAN = "progress_lt"
CONDITION_TYPE_PROGRESS_EQUAL = "progress_eq"
CONDITION_TYPE_PROGRESS_NOT_EQUAL = "progress_ne"
CONDITION_TYPE_GOAL_GREATER_THAN = "goal_gt"
CONDITION_TYPE_GOAL_LESS_THAN = "goal_lt"
CONDITION_TYPE_GOAL_EQUAL = "goal_eq"
CONDITION_TYPE_GOAL_NOT_EQUAL = "goal_ne"
CONDITION_TYPE_HIGHEST_LEVEL_GREATER_THAN = "highest_level_gt"
CONDITION_TYPE_HIGHEST_LEVEL_LESS_THAN = "highest_level_lt"
CONDITION_TYPE_HIGHEST_LEVEL_EQUAL = "highest_level_eq"
CONDITION_TYPE_HIGHEST_LEVEL_NOT_EQUAL = "highest_level_ne"
CONDITION_TYPE_HIGHEST_TOTAL_GREATER_THAN = "highest_total_gt"
CONDITION_TYPE_HIGHEST_TOTAL_LESS_THAN = "highest_total_lt"
CONDITION_TYPE_HIGHEST_TOTAL_EQUAL = "highest_total_eq"
CONDITION_TYPE_HIGHEST_TOTAL_NOT_EQUAL = "highest_total_ne"
CONDITION_TYPE_IS_SHARED = "is_shared"
CONDITION_TYPE_TRAIN_TYPE = "train_type"

BEGIN_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.HypeTrainBegin], bool]] = {
    CONDITION_TYPE_NONE: lambda value, train: True,
    CONDITION_TYPE_CHANNEL_ID: lambda value, train: value == str(train.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, train: value.lower() == train.broadcaster.name.lower(),
    CONDITION_TYPE_LEVEL_GREATER_THAN: lambda value, train: train.level > int(value),
    CONDITION_TYPE_LEVEL_LESS_THAN: lambda value, train: train.level < int(value),
    CONDITION_TYPE_LEVEL_EQUAL: lambda value, train: train.level == int(value),
    CONDITION_TYPE_LEVEL_NOT_EQUAL: lambda value, train: train.level != int(value),
    CONDITION_TYPE_TOTAL_GREATER_THAN: lambda value, train: train.total > int(value),
    CONDITION_TYPE_TOTAL_LESS_THAN: lambda value, train: train.total < int(value),
    CONDITION_TYPE_TOTAL_EQUAL: lambda value, train: train.total == int(value),
    CONDITION_TYPE_TOTAL_NOT_EQUAL: lambda value, train: train.total != int(value),
    CONDITION_TYPE_PROGRESS_GREATER_THAN: lambda value, train: train.progress > int(value),
    CONDITION_TYPE_PROGRESS_LESS_THAN: lambda value, train: train.progress < int(value),
    CONDITION_TYPE_PROGRESS_EQUAL: lambda value, train: train.progress == int(value),
    CONDITION_TYPE_PROGRESS_NOT_EQUAL: lambda value, train: train.progress != int(value),
    CONDITION_TYPE_GOAL_GREATER_THAN: lambda value, train: train.goal > int(value),
    CONDITION_TYPE_GOAL_LESS_THAN: lambda value, train: train.goal < int(value),
    CONDITION_TYPE_GOAL_EQUAL: lambda value, train: train.goal == int(value),
    CONDITION_TYPE_GOAL_NOT_EQUAL: lambda value, train: train.goal != int(value),
    CONDITION_TYPE_HIGHEST_LEVEL_GREATER_THAN: lambda value, train: train.all_time_high_level > int(value),
    CONDITION_TYPE_HIGHEST_LEVEL_LESS_THAN: lambda value, train: train.all_time_high_level < int(value),
    CONDITION_TYPE_HIGHEST_LEVEL_EQUAL: lambda value, train: train.all_time_high_level == int(value),
    CONDITION_TYPE_HIGHEST_LEVEL_NOT_EQUAL: lambda value, train: train.all_time_high_level != int(value),
    CONDITION_TYPE_HIGHEST_TOTAL_GREATER_THAN: lambda value, train: train.all_time_high_total > int(value),
    CONDITION_TYPE_HIGHEST_TOTAL_LESS_THAN: lambda value, train: train.all_time_high_total < int(value),
    CONDITION_TYPE_HIGHEST_TOTAL_EQUAL: lambda value, train: train.all_time_high_total == int(value),
    CONDITION_TYPE_HIGHEST_TOTAL_NOT_EQUAL: lambda value, train: train.all_time_high_total != int(value),
    CONDITION_TYPE_IS_SHARED: lambda value, train: value.lower() == str(train.shared_train).lower(),
    CONDITION_TYPE_TRAIN_TYPE: lambda value, train: value.lower() == train.type,
}

PROGRESS_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.HypeTrainProgress], bool]] = {
    CONDITION_TYPE_NONE: lambda value, train: True,
    CONDITION_TYPE_CHANNEL_ID: lambda value, train: value == str(train.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, train: value.lower() == train.broadcaster.name.lower(),
    CONDITION_TYPE_LEVEL_GREATER_THAN: lambda value, train: train.level > int(value),
    CONDITION_TYPE_LEVEL_LESS_THAN: lambda value, train: train.level < int(value),
    CONDITION_TYPE_LEVEL_EQUAL: lambda value, train: train.level == int(value),
    CONDITION_TYPE_LEVEL_NOT_EQUAL: lambda value, train: train.level != int(value),
    CONDITION_TYPE_TOTAL_GREATER_THAN: lambda value, train: train.total > int(value),
    CONDITION_TYPE_TOTAL_LESS_THAN: lambda value, train: train.total < int(value),
    CONDITION_TYPE_TOTAL_EQUAL: lambda value, train: train.total == int(value),
    CONDITION_TYPE_TOTAL_NOT_EQUAL: lambda value, train: train.total != int(value),
    CONDITION_TYPE_PROGRESS_GREATER_THAN: lambda value, train: train.progress > int(value),
    CONDITION_TYPE_PROGRESS_LESS_THAN: lambda value, train: train.progress < int(value),
    CONDITION_TYPE_PROGRESS_EQUAL: lambda value, train: train.progress == int(value),
    CONDITION_TYPE_PROGRESS_NOT_EQUAL: lambda value, train: train.progress != int(value),
    CONDITION_TYPE_GOAL_GREATER_THAN: lambda value, train: train.goal > int(value),
    CONDITION_TYPE_GOAL_LESS_THAN: lambda value, train: train.goal < int(value),
    CONDITION_TYPE_GOAL_EQUAL: lambda value, train: train.goal == int(value),
    CONDITION_TYPE_GOAL_NOT_EQUAL: lambda value, train: train.goal != int(value),
    CONDITION_TYPE_IS_SHARED: lambda value, train: value.lower() == str(train.shared_train).lower(),
    CONDITION_TYPE_TRAIN_TYPE: lambda value, train: value.lower() == train.type,
}

END_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.HypeTrainEnd], bool]] = {
    CONDITION_TYPE_NONE: lambda value, train: True,
    CONDITION_TYPE_CHANNEL_ID: lambda value, train: value == str(train.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, train: value.lower() == train.broadcaster.name.lower(),
    CONDITION_TYPE_LEVEL_GREATER_THAN: lambda value, train: train.level > int(value),
    CONDITION_TYPE_LEVEL_LESS_THAN: lambda value, train: train.level < int(value),
    CONDITION_TYPE_LEVEL_EQUAL: lambda value, train: train.level == int(value),
    CONDITION_TYPE_LEVEL_NOT_EQUAL: lambda value, train: train.level != int(value),
    CONDITION_TYPE_TOTAL_GREATER_THAN: lambda value, train: train.total > int(value),
    CONDITION_TYPE_TOTAL_LESS_THAN: lambda value, train: train.total < int(value),
    CONDITION_TYPE_TOTAL_EQUAL: lambda value, train: train.total == int(value),
    CONDITION_TYPE_TOTAL_NOT_EQUAL: lambda value, train: train.total != int(value),
    CONDITION_TYPE_IS_SHARED: lambda value, train: value.lower() == str(train.shared_train).lower(),
    CONDITION_TYPE_TRAIN_TYPE: lambda value, train: value.lower() == train.type,
}

HypeTrainBeginTrigger = event_triggers.EventTrigger[twitchio.HypeTrainBegin]

class ActionHypeTrainBeginTrigger(event_triggers.ActionEventTrigger[twitchio.HypeTrainBegin]):
    TYPE_NAME = "twitch_train_begin"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, train_begin=event)
    
class CallbackHypeTrainBeginTrigger(event_triggers.CallbackEventTrigger[twitchio.HypeTrainBegin]):
    pass

HypeTrainProgressTrigger = event_triggers.EventTrigger[twitchio.HypeTrainProgress]

class ActionHypeTrainProgressTrigger(event_triggers.ActionEventTrigger[twitchio.HypeTrainProgress]):
    TYPE_NAME = "twitch_train_progress"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, train_progress=event)
    
class CallbackHypeTrainProgressTrigger(event_triggers.CallbackEventTrigger[twitchio.HypeTrainProgress]):
    pass

HypeTrainEndTrigger = event_triggers.EventTrigger[twitchio.HypeTrainEnd]

class ActionHypeTrainEndTrigger(event_triggers.ActionEventTrigger[twitchio.HypeTrainEnd]):
    TYPE_NAME = "twitch_train_end"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, train_end=event)
    
class CallbackHypeTrainEndTrigger(event_triggers.CallbackEventTrigger[twitchio.HypeTrainEnd]):
    pass

callback_hypetrain_begin_triggers:dict[str, HypeTrainBeginTrigger] = {}
callback_hypetrain_progress_triggers:dict[str, HypeTrainProgressTrigger] = {}
callback_hypetrain_end_triggers:dict[str, HypeTrainEndTrigger] = {}

merge_hypetrain_begin_triggers = actions.create_triggers_merge_function(HypeTrainBeginTrigger, ActionHypeTrainBeginTrigger, callback_hypetrain_begin_triggers)
merge_hypetrain_progress_triggers = actions.create_triggers_merge_function(HypeTrainProgressTrigger, ActionHypeTrainProgressTrigger, callback_hypetrain_progress_triggers)
merge_hypetrain_end_triggers = actions.create_triggers_merge_function(HypeTrainEndTrigger, ActionHypeTrainEndTrigger, callback_hypetrain_end_triggers)
