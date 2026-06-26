from . import event_triggers, tronix_integrations as tti
import actions
import re
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"
CONDITION_TYPE_TIER = "tier"
CONDITION_TYPE_IS_GIFTED = "is_gifted"
CONDITION_TYPE_GIFTED_GREATER_THAN = "gifted_gt"
CONDITION_TYPE_GIFTED_LESS_THAN = "gifted_lt"
CONDITION_TYPE_GIFTED_EQUAL = "gifted_eq"
CONDITION_TYPE_GIFTED_NOT_EQUAL = "gifted_ne"
#CONDITION_TYPE_IS_PRIME = "prime" #TODO figure out how to check for prime
CONDITION_TYPE_USER_ID = "user_id"
CONDITION_TYPE_USER_NAME = "user_name"
CONDITION_TYPE_CHANNEL_ID = "channel_id"
CONDITION_TYPE_CHANNEL_NAME = "channel_name"
CONDITION_TYPE_IS_ANONYMOUS = "is_anonymous"
CONDITION_TYPE_MONTHS_GREATER_THAN = "months_gt"
CONDITION_TYPE_MONTHS_LESS_THAN = "months_lt"
CONDITION_TYPE_MONTHS_EQUAL = "months_eq"
CONDITION_TYPE_MONTHS_NOT_EQUAL = "months_ne"
CONDITION_TYPE_CUMULATIVE_MONTHS_GREATER_THAN = "cumulative_months_gt"
CONDITION_TYPE_CUMULATIVE_MONTHS_LESS_THAN = "cumulative_months_lt"
CONDITION_TYPE_CUMULATIVE_MONTHS_EQUAL = "cumulative_months_eq"
CONDITION_TYPE_CUMULATIVE_MONTHS_NOT_EQUAL = "cumulative_months_ne"
CONDITION_TYPE_STREAK_MONTHS_GREATER_THAN = "streak_months_gt"
CONDITION_TYPE_STREAK_MONTHS_LESS_THAN = "streak_months_lt"
CONDITION_TYPE_STREAK_MONTHS_EQUAL = "streak_months_eq"
CONDITION_TYPE_STREAK_MONTHS_NOT_EQUAL = "streak_months_ne"
CONDITION_TYPE_MSG_PREFIX = "msg_prefix"
CONDITION_TYPE_MSG_SUFFIX = "msg_suffix"
CONDITION_TYPE_MSG_CONTAINS = "msg_contains"
CONDITION_TYPE_MSG_REGEX = "msg_regex"

Sub_T = twitchio.ChannelSubscribe|twitchio.ChannelSubscriptionGift

SUB_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelSubscribe], bool]] = {
    CONDITION_TYPE_NONE: lambda value, sub: True,
    CONDITION_TYPE_TIER: lambda value, sub: value == sub.tier,
    CONDITION_TYPE_IS_GIFTED: lambda value, sub: value.lower() == str(sub.gift).lower(),
    CONDITION_TYPE_GIFTED_GREATER_THAN: lambda value, sub: False,
    CONDITION_TYPE_GIFTED_LESS_THAN: lambda value, sub: False,
    CONDITION_TYPE_GIFTED_EQUAL: lambda value, sub: False,
    CONDITION_TYPE_GIFTED_NOT_EQUAL: lambda value, sub: False,
    CONDITION_TYPE_USER_ID: lambda value, sub: value == str(sub.user.id),
    CONDITION_TYPE_USER_NAME: lambda value, sub: value.lower() == sub.user.name.lower(),
    CONDITION_TYPE_CHANNEL_ID: lambda value, sub: value == str(sub.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, sub: value.lower() == sub.broadcaster.name.lower(),
    CONDITION_TYPE_IS_ANONYMOUS: lambda value, sub: value.lower() == "false"
}

GSUB_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelSubscriptionGift], bool]] = {
    CONDITION_TYPE_NONE: lambda value, sub: True,
    CONDITION_TYPE_TIER: lambda value, sub: value == sub.tier,
    CONDITION_TYPE_IS_GIFTED: lambda value, sub: value.lower() == "true",
    CONDITION_TYPE_GIFTED_GREATER_THAN: lambda value, sub: sub.total > int(value),
    CONDITION_TYPE_GIFTED_LESS_THAN: lambda value, sub: sub.total < int(value),
    CONDITION_TYPE_GIFTED_EQUAL: lambda value, sub: sub.total == int(value),
    CONDITION_TYPE_GIFTED_NOT_EQUAL: lambda value, sub: sub.total != int(value),
    CONDITION_TYPE_USER_ID: lambda value, sub: not sub.anonymous and value == str(sub.user.id),
    CONDITION_TYPE_USER_NAME: lambda value, sub: not sub.anonymous and value.lower() == sub.user.name.lower(),
    CONDITION_TYPE_CHANNEL_ID: lambda value, sub: value == str(sub.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, sub: value.lower() == sub.broadcaster.name.lower(),
    CONDITION_TYPE_IS_ANONYMOUS: lambda value, sub: value.lower() == str(sub.anonymous).lower()
}

SUB_MSG_CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelSubscriptionMessage], bool]] = {
    CONDITION_TYPE_NONE: lambda value, sub: True,
    CONDITION_TYPE_TIER: lambda value, sub: value == sub.tier,
    CONDITION_TYPE_IS_GIFTED: lambda value, sub: value.lower() == "false",
    CONDITION_TYPE_GIFTED_GREATER_THAN: lambda value, sub: False,
    CONDITION_TYPE_GIFTED_LESS_THAN: lambda value, sub: False,
    CONDITION_TYPE_GIFTED_EQUAL: lambda value, sub: False,
    CONDITION_TYPE_GIFTED_NOT_EQUAL: lambda value, sub: False,
    CONDITION_TYPE_USER_ID: lambda value, sub: value == str(sub.user.id),
    CONDITION_TYPE_USER_NAME: lambda value, sub: value.lower() == sub.user.name.lower(),
    CONDITION_TYPE_CHANNEL_ID: lambda value, sub: value == str(sub.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, sub: value.lower() == sub.broadcaster.name.lower(),
    CONDITION_TYPE_IS_ANONYMOUS: lambda value, sub: value.lower() == "false",
    CONDITION_TYPE_MONTHS_GREATER_THAN: lambda value, sub: sub.months > int(value),
    CONDITION_TYPE_MONTHS_LESS_THAN: lambda value, sub: sub.months < int(value),
    CONDITION_TYPE_MONTHS_EQUAL: lambda value, sub: sub.months == int(value),
    CONDITION_TYPE_MONTHS_NOT_EQUAL: lambda value, sub: sub.months != int(value),
    CONDITION_TYPE_CUMULATIVE_MONTHS_GREATER_THAN: lambda value, sub: sub.cumulative_months > int(value),
    CONDITION_TYPE_CUMULATIVE_MONTHS_LESS_THAN: lambda value, sub: sub.cumulative_months < int(value),
    CONDITION_TYPE_CUMULATIVE_MONTHS_EQUAL: lambda value, sub: sub.cumulative_months == int(value),
    CONDITION_TYPE_CUMULATIVE_MONTHS_NOT_EQUAL: lambda value, sub: sub.cumulative_months != int(value),
    CONDITION_TYPE_STREAK_MONTHS_GREATER_THAN: lambda value, sub: sub.streak_months > int(value),
    CONDITION_TYPE_STREAK_MONTHS_LESS_THAN: lambda value, sub: sub.streak_months < int(value),
    CONDITION_TYPE_STREAK_MONTHS_EQUAL: lambda value, sub: sub.streak_months == int(value),
    CONDITION_TYPE_STREAK_MONTHS_NOT_EQUAL: lambda value, sub: sub.streak_months != int(value),
    CONDITION_TYPE_MSG_PREFIX: lambda value, sub: sub.text.startswith(value),
    CONDITION_TYPE_MSG_SUFFIX: lambda value, sub: sub.text.endswith(value),
    CONDITION_TYPE_MSG_CONTAINS: lambda value, sub: value in sub.text,
    CONDITION_TYPE_MSG_REGEX: lambda value, sub: re.match(value, sub.text),
}


SubTrigger = event_triggers.EventTrigger[twitchio.ChannelSubscribe]
GiftSubTrigger = event_triggers.EventTrigger[twitchio.ChannelSubscriptionGift]
SubMessageTrigger = event_triggers.EventTrigger[twitchio.ChannelSubscriptionMessage]
    
class ActionSubTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelSubscribe]):
    TYPE_NAME = "twitch_sub"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, sub=event)
    
class CallbackSubTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelSubscribe]):
    pass

class ActionGiftSubTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelSubscriptionGift]):
    TYPE_NAME = "twitch_gift_sub"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, gift_sub=event)
    
class CallbackGiftSubTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelSubscriptionGift]):
    pass

class ActionSubMessageTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelSubscriptionMessage]):
    TYPE_NAME = "twitch_sub_message"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, sub_msg=event)
    
class CallbackSubMessageTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelSubscriptionMessage]):
    pass


callback_sub_triggers:dict[str, CallbackSubTrigger] = {}
callback_gift_sub_triggers:dict[str, CallbackGiftSubTrigger] = {}
callback_sub_msg_triggers:dict[str, CallbackSubMessageTrigger] = {}

merge_sub_triggers = actions.create_triggers_merge_function(SubTrigger, ActionSubTrigger, callback_sub_triggers)
merge_gift_sub_triggers = actions.create_triggers_merge_function(GiftSubTrigger, ActionGiftSubTrigger, callback_gift_sub_triggers)
merge_sub_msg_triggers = actions.create_triggers_merge_function(SubMessageTrigger, ActionSubMessageTrigger, callback_sub_msg_triggers)
