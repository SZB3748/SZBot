from . import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"
CONDITION_TYPE_FROM_CHANNEL_ID = "from_channel_id"
CONDITION_TYPE_FROM_CHANNEL_NAME = "from_channel_name"
CONDITION_TYPE_TO_CHANNEL_ID = "to_channel_id"
CONDITION_TYPE_TO_CHANNEL_NAME = "to_channel_name"
CONDITION_TYPE_VIEWCOUNT_GREATER_THAN = "viewcount_gt"
CONDITION_TYPE_VIEWCOUNT_LESS_THAN = "viewcount_lt"
CONDITION_TYPE_VIEWCOUNT_EQUAL = "viewcount_eq"
CONDITION_TYPE_VIEWCOUNT_NOT_EQUAL = "viewcount_ne"

CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelRaid], bool]] = {
    CONDITION_TYPE_NONE: lambda value, raid: True,
    CONDITION_TYPE_FROM_CHANNEL_ID: lambda value, raid: value == str(raid.from_broadcaster.id),
    CONDITION_TYPE_FROM_CHANNEL_NAME: lambda value, raid: value.lower() == raid.from_broadcaster.name.lower(),
    CONDITION_TYPE_TO_CHANNEL_ID: lambda value, raid: value == str(raid.to_broadcaster.id),
    CONDITION_TYPE_TO_CHANNEL_NAME: lambda value, raid: value.lower() == raid.to_broadcaster.name.lower(),
    CONDITION_TYPE_VIEWCOUNT_GREATER_THAN: lambda value, raid: raid.viewer_count > int(value),
    CONDITION_TYPE_VIEWCOUNT_LESS_THAN: lambda value, raid: raid.viewer_count < int(value),
    CONDITION_TYPE_VIEWCOUNT_EQUAL: lambda value, raid: raid.viewer_count == int(value),
    CONDITION_TYPE_VIEWCOUNT_NOT_EQUAL: lambda value, raid: raid.viewer_count != int(value),
}

RaidTrigger = event_triggers.EventTrigger[twitchio.ChannelRaid]

class ActionRaidTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelRaid]):
    TYPE_NAME = "twitch_raid"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, raid=event)
    
class CallbackRaidTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelRaid]):
    pass

callback_raid_triggers:dict[str, CallbackRaidTrigger] = {}

merge_raid_triggers = actions.create_triggers_merge_function(RaidTrigger, ActionRaidTrigger, callback_raid_triggers)
