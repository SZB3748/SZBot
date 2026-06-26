from . import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"
CONDITION_TYPE_USER_ID = "user_id"
CONDITION_TYPE_USER_NAME = "user_name"
CONDITION_TYPE_CHANNEL_ID = "channel_id"
CONDITION_TYPE_CHANNEL_NAME = "channel_name"

CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelFollow], bool]] = {
    CONDITION_TYPE_NONE: lambda value, follow: True,
    CONDITION_TYPE_USER_ID: lambda value, follow: not value == str(follow.user.id),
    CONDITION_TYPE_USER_NAME: lambda value, follow: not value.lower() == follow.user.name.lower(),
    CONDITION_TYPE_CHANNEL_ID: lambda value, follow: value == str(follow.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, follow: value.lower() == follow.broadcaster.name.lower(),
}

FollowTrigger = event_triggers.EventTrigger[twitchio.ChannelFollow]

class ActionFollowTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelFollow]):
    TYPE_NAME = "twitch_follow"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, follow=event)
    
class CallbackFollowTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelFollow]):
    pass

callback_follow_triggers:dict[str, CallbackFollowTrigger] = {}

merge_follow_triggers = actions.create_triggers_merge_function(FollowTrigger, ActionFollowTrigger, callback_follow_triggers)
