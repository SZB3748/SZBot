from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"

DONATE_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.CharityCampaignDonation], bool]] = {
    CONDITION_TYPE_NONE: lambda value, donation: True
}

START_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.CharityCampaignStart], bool]] = {
    CONDITION_TYPE_NONE: lambda value, start: True
}

PROGRESS_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.CharityCampaignProgress], bool]] = {
    CONDITION_TYPE_NONE: lambda value, progress: True
}

STOP_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.CharityCampaignStop], bool]] = {
    CONDITION_TYPE_NONE: lambda value, stop: True
}

ChairtyDonateTrigger = event_triggers.EventTrigger[twitchio.CharityDonation]

class ActionChairtyDonateTrigger(event_triggers.ActionEventTrigger[twitchio.CharityDonation]):
    TYPE_NAME = "twitch_charity_donate"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, charity_donate=event)
    
class CallbackChairtyDonateTrigger(event_triggers.CallbackEventTrigger[twitchio.CharityDonation]):
    pass

ChairtyStartTrigger = event_triggers.EventTrigger[twitchio.CharityCampaignStart]

class ActionChairtyStartTrigger(event_triggers.ActionEventTrigger[twitchio.CharityCampaignStart]):
    TYPE_NAME = "twitch_charity_start"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, charity_start=event)
    
class CallbackChairtyStartTrigger(event_triggers.CallbackEventTrigger[twitchio.CharityCampaignStart]):
    pass

ChairtyProgressTrigger = event_triggers.EventTrigger[twitchio.CharityCampaignProgress]

class ActionChairtyProgressTrigger(event_triggers.ActionEventTrigger[twitchio.CharityCampaignProgress]):
    TYPE_NAME = "twitch_charity_progress"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, charity_progress=event)
    
class CallbackChairtyProgressTrigger(event_triggers.CallbackEventTrigger[twitchio.CharityCampaignProgress]):
    pass

ChairtyStopTrigger = event_triggers.EventTrigger[twitchio.CharityCampaignStop]

class ActionChairtyStopTrigger(event_triggers.ActionEventTrigger[twitchio.CharityCampaignStop]):
    TYPE_NAME = "twitch_charity_stop"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, charity_stop=event)
    
class CallbackChairtyStopTrigger(event_triggers.CallbackEventTrigger[twitchio.CharityCampaignStop]):
    pass

callback_chairty_donate_triggers:dict[str, CallbackChairtyDonateTrigger] = {}
callback_chairty_start_triggers:dict[str, CallbackChairtyStartTrigger] = {}
callback_chairty_progress_triggers:dict[str, CallbackChairtyProgressTrigger] = {}
callback_chairty_stop_triggers:dict[str, CallbackChairtyStopTrigger] = {}

merge_chairty_donate_triggers = actions.create_triggers_merge_function(ChairtyDonateTrigger, ActionChairtyDonateTrigger, callback_chairty_donate_triggers)
merge_chairty_start_triggers = actions.create_triggers_merge_function(ChairtyStartTrigger, ActionChairtyStartTrigger, callback_chairty_start_triggers)
merge_chairty_progress_triggers = actions.create_triggers_merge_function(ChairtyProgressTrigger, ActionChairtyProgressTrigger, callback_chairty_progress_triggers)
merge_chairty_stop_triggers = actions.create_triggers_merge_function(ChairtyStopTrigger, ActionChairtyStopTrigger, callback_chairty_stop_triggers)