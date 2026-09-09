from .. import event_triggers, tronix_integrations as tti
import actions
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"

BEGIN_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.SharedChatSessionBegin], bool]] = {
    CONDITION_TYPE_NONE: lambda value, begin: True
}

UPDATE_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.SharedChatSessionUpdate], bool]] = {
    CONDITION_TYPE_NONE: lambda value, update: True
}

END_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.SharedChatSessionEnd], bool]] = {
    CONDITION_TYPE_NONE: lambda value, end: True
}

SharedChatBeginTrigger = event_triggers.EventTrigger[twitchio.SharedChatSessionBegin]

class ActionSharedChatBeginTrigger(event_triggers.ActionEventTrigger[twitchio.SharedChatSessionBegin]):
    TYPE_NAME = "twitch_shared_chat_begin"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, shared_chat_begin=event)
    
class CallbackSharedChatBeginTrigger(event_triggers.CallbackEventTrigger[twitchio.SharedChatSessionBegin]):
    pass

SharedChatUpdateTrigger = event_triggers.EventTrigger[twitchio.SharedChatSessionUpdate]

class ActionSharedChatUpdateTrigger(event_triggers.ActionEventTrigger[twitchio.SharedChatSessionUpdate]):
    TYPE_NAME = "twitch_shared_chat_update"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, shared_chat_update=event)
    
class CallbackSharedChatUpdateTrigger(event_triggers.CallbackEventTrigger[twitchio.SharedChatSessionUpdate]):
    pass

SharedChatEndTrigger = event_triggers.EventTrigger[twitchio.SharedChatSessionEnd]

class ActionSharedChatEndTrigger(event_triggers.ActionEventTrigger[twitchio.SharedChatSessionEnd]):
    TYPE_NAME = "twitch_shared_chat_end"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, shared_chat_end=event)
    
class CallbackSharedChatEndTrigger(event_triggers.CallbackEventTrigger[twitchio.SharedChatSessionEnd]):
    pass

callback_shared_chat_begin_triggers:dict[str, CallbackSharedChatBeginTrigger] = {}
callback_shared_chat_update_triggers:dict[str, CallbackSharedChatUpdateTrigger] = {}
callback_shared_chat_end_triggers:dict[str, CallbackSharedChatEndTrigger] = {}

merge_shared_chat_begin_triggers = actions.create_triggers_merge_function(SharedChatBeginTrigger, ActionSharedChatBeginTrigger, callback_shared_chat_begin_triggers)
merge_shared_chat_update_triggers = actions.create_triggers_merge_function(SharedChatUpdateTrigger, ActionSharedChatUpdateTrigger, callback_shared_chat_update_triggers)
merge_shared_chat_end_triggers = actions.create_triggers_merge_function(SharedChatEndTrigger, ActionSharedChatEndTrigger, callback_shared_chat_end_triggers)
