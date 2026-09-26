from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"

CLEAR_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelChatClear], bool]] = {
    CONDITION_TYPE_NONE: lambda value, clear: True
}

CLEAR_USER_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelChatClearUserMessages], bool]] = {
    CONDITION_TYPE_NONE: lambda value, clear: True
}

ChatClearTrigger = event_triggers.EventTrigger[twitchio.ChannelChatClear]

class ActionChatClearTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelChatClear]):
    TYPE_NAME = "twitch_chat_clear"

class CallbackChatClearTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelChatClear]):
    pass

ChatClearUserTrigger = event_triggers.EventTrigger[twitchio.ChannelChatClearUserMessages]

class ActionChatClearUserTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelChatClearUserMessages]):
    TYPE_NAME = "twitch_chat_user_clear"

class CallbackChatClearUserTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelChatClearUserMessages]):
    pass

callback_chat_clear_triggers:dict[str, CallbackChatClearTrigger] = {}
callback_chat_clear_user_triggers:dict[str, CallbackChatClearUserTrigger] = {}

merge_chat_clear_triggers = actions.create_triggers_merge_function(ChatClearTrigger, ActionChatClearTrigger, callback_chat_clear_triggers)
merge_chat_clear_user_triggers = actions.create_triggers_merge_function(ChatClearUserTrigger, ActionChatClearUserTrigger, callback_chat_clear_user_triggers)
