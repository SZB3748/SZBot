from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPES_NONE = "none"

BAN_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelBan], bool]] = {
    CONDITION_TYPES_NONE: lambda value, ban: True
}

UNBAN_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelUnban], bool]] = {
    CONDITION_TYPES_NONE: lambda value, unban: True
}

BanTrigger = event_triggers.EventTrigger[twitchio.ChannelBan]

class ActionBanTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelBan]):
    TYPE_NAME = "twitch_ban"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, ban=event)

class CallbackBanTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelBan]):
    pass

UnbanTrigger = event_triggers.EventTrigger[twitchio.ChannelUnban]

class ActionUnbanTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelUnban]):
    TYPE_NAME = "twitch_unban"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, unban=event)

class CallbackUnbanTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelUnban]):
    pass

callback_ban_triggers:dict[str, CallbackBanTrigger] = {}
callback_unban_triggers:dict[str, CallbackUnbanTrigger] = {}

merge_ban_triggers = actions.create_triggers_merge_function(BanTrigger, ActionBanTrigger, callback_ban_triggers)
merge_unban_triggers = actions.create_triggers_merge_function(UnbanTrigger, ActionUnbanTrigger, callback_unban_triggers)
