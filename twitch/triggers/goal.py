from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"

BEGIN_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.GoalBegin], bool]] = {
    CONDITION_TYPE_NONE: lambda value, begin: True
}

PROGRESS_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.GoalProgress], bool]] = {
    CONDITION_TYPE_NONE: lambda value, progress: True
}

END_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.GoalEnd], bool]] = {
    CONDITION_TYPE_NONE: lambda value, end: True
}

GoalBeginTrigger = event_triggers.EventTrigger[twitchio.GoalBegin]

class ActionGoalBeginTrigger(event_triggers.ActionEventTrigger[twitchio.GoalBegin]):
    TYPE_NAME = "twitch_goal_begin"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, goal_begin=event)
    
class CallbackGoalBeginTrigger(event_triggers.CallbackEventTrigger[twitchio.GoalBegin]):
    pass

GoalProgressTrigger = event_triggers.EventTrigger[twitchio.GoalProgress]

class ActionGoalProgressTrigger(event_triggers.ActionEventTrigger[twitchio.GoalProgress]):
    TYPE_NAME = "twitch_goal_progress"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, goal_progress=event)
    
class CallbackGoalProgressTrigger(event_triggers.CallbackEventTrigger[twitchio.GoalProgress]):
    pass

GoalEndTrigger = event_triggers.EventTrigger[twitchio.GoalEnd]

class ActionGoalEndTrigger(event_triggers.ActionEventTrigger[twitchio.GoalEnd]):
    TYPE_NAME = "twitch_goal_end"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, goal_end=event)
    
class CallbackGoalEndTrigger(event_triggers.CallbackEventTrigger[twitchio.GoalEnd]):
    pass

callback_goal_begin_triggers:dict[str, CallbackGoalBeginTrigger] = {}
callback_goal_progress_triggers:dict[str, CallbackGoalProgressTrigger] = {}
callback_goal_end_triggers:dict[str, CallbackGoalEndTrigger] = {}

merge_goal_begin_triggers = actions.create_triggers_merge_function(GoalBeginTrigger, ActionGoalBeginTrigger, callback_goal_begin_triggers)
merge_goal_progress_triggers = actions.create_triggers_merge_function(GoalProgressTrigger, ActionGoalProgressTrigger, callback_goal_progress_triggers)
merge_goal_end_triggers = actions.create_triggers_merge_function(GoalEndTrigger, ActionGoalEndTrigger, callback_goal_end_triggers)
