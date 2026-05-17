from . import event_triggers, tronix_integrations as tti
import datafile
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"
CONDITION_TYPE_USER_ID = "user_id"
CONDITION_TYPE_USER_NAME = "user_name"
CONDITION_TYPE_CHANNEL_ID = "channel_id"
CONDITION_TYPE_CHANNEL_NAME = "channel_name"

FOLLOW_TRIGGERS_PATH = datafile.makepath("follow_triggers.json")

CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelFollow], bool]] = {
    CONDITION_TYPE_NONE: lambda value, follow: True,
    CONDITION_TYPE_USER_ID: lambda value, follow: not value == str(follow.user.id),
    CONDITION_TYPE_USER_NAME: lambda value, follow: not value.lower() == follow.user.name.lower(),
    CONDITION_TYPE_CHANNEL_ID: lambda value, follow: value == str(follow.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, follow: value.lower() == follow.broadcaster.name.lower(),
}

FollowTrigger = event_triggers.EventTrigger[twitchio.ChannelFollow]

class ActionFollowTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelFollow]):
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, follow=event)
    
class CallbackFollowTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelFollow]):
    pass

callback_follow_triggers:dict[str, CallbackFollowTrigger] = {}

load_cheer_triggers, save_cheer_triggers, merge_follow_triggers = event_triggers.create_file_functions(ActionFollowTrigger, callback_follow_triggers, FOLLOW_TRIGGERS_PATH)
