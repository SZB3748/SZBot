from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"

MOD_ADD_MATCHERS = {
    CONDITION_TYPE_NONE: lambda value, add: True
}

MOD_REMOVE_MATCHERS = {
    CONDITION_TYPE_NONE: lambda value, add: True
}

VIP_ADD_MATCHERS = {
    CONDITION_TYPE_NONE: lambda value, add: True
}

VIP_REMOVE_MATCHERS = {
    CONDITION_TYPE_NONE: lambda value, add: True
}


ModAddTrigger = event_triggers.EventTrigger[twitchio.ChannelModeratorAdd]

class ActionModAddTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelModeratorAdd]):
    TYPE_NAME = "twitch_mod_add"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, mod_add=event)

class CallbackModAddTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelModeratorAdd]):
    pass

ModRemoveTrigger = event_triggers.EventTrigger[twitchio.ChannelModeratorRemove]

class ActionModRemoveTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelModeratorRemove]):
    TYPE_NAME = "twitch_mod_remove"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, mod_remove=event)

class CallbackModRemoveTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelModeratorRemove]):
    pass

VIPAddTrigger = event_triggers.EventTrigger[twitchio.ChannelVIPAdd]

class ActionVIPAddTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelVIPAdd]):
    TYPE_NAME = "twitch_vip_add"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, vip_add=event)

class CallbackVIPAddTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelVIPAdd]):
    pass

VIPRemoveTrigger = event_triggers.EventTrigger[twitchio.ChannelVIPRemove]

class ActionVIPRemoveTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelVIPRemove]):
    TYPE_NAME = "twitch_vip_remove"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, vip_remove=event)

class CallbackVIPRemoveTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelVIPRemove]):
    pass

callback_mod_add_triggers:dict[str, CallbackModAddTrigger] = {}
callback_mod_remove_triggers:dict[str, CallbackModRemoveTrigger] = {}
callback_vip_add_triggers:dict[str, CallbackVIPAddTrigger] = {}
callback_vip_remove_triggers:dict[str, CallbackVIPRemoveTrigger] = {}

merge_mod_add_triggers = actions.create_triggers_merge_function(ModAddTrigger, ActionModAddTrigger, callback_mod_add_triggers)
merge_mod_remove_triggers = actions.create_triggers_merge_function(ModRemoveTrigger, ActionModRemoveTrigger, callback_mod_remove_triggers)
merge_vip_add_triggers = actions.create_triggers_merge_function(VIPAddTrigger, ActionVIPAddTrigger, callback_vip_add_triggers)
merge_vip_remove_triggers = actions.create_triggers_merge_function(VIPRemoveTrigger, ActionVIPRemoveTrigger, callback_vip_remove_triggers)
