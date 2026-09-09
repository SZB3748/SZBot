from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"

BEGIN_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelPollBegin], bool]] = {
    CONDITION_TYPE_NONE: lambda value, begin: True
}

PROGRESS_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelPollProgress], bool]] = {
    CONDITION_TYPE_NONE: lambda value, progress: True
}

END_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelPollEnd], bool]] = {
    CONDITION_TYPE_NONE: lambda value, end: True
}

PollBeginTrigger = event_triggers.EventTrigger[twitchio.ChannelPollBegin]

class ActionPollBeginTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelPollBegin]):
    TYPE_NAME = "twitch_poll_begin"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, poll_begin=event)
    
class CallbackPollBeginTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelPollBegin]):
    pass

PollProgressTrigger = event_triggers.EventTrigger[twitchio.ChannelPollProgress]

class ActionPollProgressTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelPollProgress]):
    TYPE_NAME = "twitch_poll_progress"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, poll_progress=event)
    
class CallbackPollProgressTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelPollProgress]):
    pass

PollEndTrigger = event_triggers.EventTrigger[twitchio.ChannelPollEnd]

class ActionPollEndTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelPollEnd]):
    TYPE_NAME = "twitch_poll_end"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, poll_end=event)
    
class CallbackPollEndTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelPollEnd]):
    pass

callback_poll_begin_triggers:dict[str, CallbackPollBeginTrigger] = {}
callback_poll_progress_triggers:dict[str, CallbackPollProgressTrigger] = {}
callback_poll_end_triggers:dict[str, CallbackPollEndTrigger] = {}

merge_poll_begin_triggers = actions.create_triggers_merge_function(PollBeginTrigger, ActionPollBeginTrigger, callback_poll_begin_triggers)
merge_poll_progress_triggers = actions.create_triggers_merge_function(PollProgressTrigger, ActionPollProgressTrigger, callback_poll_progress_triggers)
merge_poll_end_triggers = actions.create_triggers_merge_function(PollEndTrigger, ActionPollEndTrigger, callback_poll_end_triggers)
