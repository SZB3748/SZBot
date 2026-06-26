from . import event_triggers, tronix_integrations as tti
import actions
import re
import twitchio
from typing import Callable

CONDITION_TYPE_NONE = "none"
CONDITION_TYPE_USER_ID = "user_id"
CONDITION_TYPE_USER_NAME = "user_name"
CONDITION_TYPE_CHANNEL_ID = "channel_id"
CONDITION_TYPE_CHANNEL_NAME = "channel_name"
CONDITION_TYPE_MSG_PREFIX = "msg_prefix"
CONDITION_TYPE_MSG_SUFFIX = "msg_suffix"
CONDITION_TYPE_MSG_CONTAINS = "msg_contains"
CONDITION_TYPE_MSG_REGEX = "msg_regex"
CONDITION_TYPE_STATUS = "status"
CONDITION_TYPE_REWARD_ID = "reward_id"
CONDITION_TYPE_REWARD_TITLE = "reward_title"
CONDITION_TYPE_REWARD_COST_GREATER_THAN = "reward_cost_gt"
CONDITION_TYPE_REWARD_COST_LESS_THAN = "reward_cost_lt"
CONDITION_TYPE_REWARD_COST_EQUAL = "reward_cost_eq"
CONDITION_TYPE_REWARD_COST_NOT_EQUAL = "reward_cost_ne"
CONDITION_TYPE_REWARD_CURRENT_COUNT_GREATER_THAN = "reward_current_count_gt"
CONDITION_TYPE_REWARD_CURRENT_COUNT_LESS_THAN = "reward_current_count_lt"
CONDITION_TYPE_REWARD_CURRENT_COUNT_EQUAL = "reward_current_count_eq"
CONDITION_TYPE_REWARD_CURRENT_COUNT_NOT_EQUAL = "reward_current_count_ne"


CONDITION_MATCHERS:dict[str, Callable[[str, twitchio.ChannelPointsRedemptionAdd], bool]] = {
    CONDITION_TYPE_NONE: lambda value, redeem: True,
    CONDITION_TYPE_USER_ID: lambda value, redeem: value == str(redeem.user.id),
    CONDITION_TYPE_USER_NAME: lambda value, redeem: value.lower() == str(redeem.user.name).lower(),
    CONDITION_TYPE_CHANNEL_ID: lambda value, redeem: value == str(redeem.broadcaster.id),
    CONDITION_TYPE_CHANNEL_NAME: lambda value, redeem: value.lower() == str(redeem.broadcaster.name).lower(),
    CONDITION_TYPE_MSG_PREFIX: lambda value, redeem: redeem.user_input.startswith(value),
    CONDITION_TYPE_MSG_SUFFIX: lambda value, redeem: redeem.user_input.endswith(value),
    CONDITION_TYPE_MSG_CONTAINS: lambda value, redeem: value in redeem.user_input,
    CONDITION_TYPE_MSG_REGEX: lambda value, redeem: re.match(value, redeem.user_input),
    CONDITION_TYPE_STATUS: lambda value, redeem: value.lower() == redeem.status.lower(),
    CONDITION_TYPE_REWARD_ID: lambda value, redeem: value == str(redeem.reward.id),
    CONDITION_TYPE_REWARD_TITLE: lambda value, redeem: value == str(redeem.reward.title),
    CONDITION_TYPE_REWARD_COST_GREATER_THAN: lambda value, redeem: redeem.reward.cost > int(value),
    CONDITION_TYPE_REWARD_COST_LESS_THAN: lambda value, redeem: redeem.reward.cost < int(value),
    CONDITION_TYPE_REWARD_COST_EQUAL: lambda value, redeem: redeem.reward.cost == int(value),
    CONDITION_TYPE_REWARD_COST_NOT_EQUAL: lambda value, redeem: redeem.reward.cost != int(value),
    CONDITION_TYPE_REWARD_CURRENT_COUNT_GREATER_THAN: lambda value, redeem: redeem.reward.current_stream_redeems > int(value),
    CONDITION_TYPE_REWARD_CURRENT_COUNT_LESS_THAN: lambda value, redeem: redeem.reward.current_stream_redeems < int(value),
    CONDITION_TYPE_REWARD_CURRENT_COUNT_EQUAL: lambda value, redeem: redeem.reward.current_stream_redeems == int(value),
    CONDITION_TYPE_REWARD_CURRENT_COUNT_NOT_EQUAL: lambda value, redeem: redeem.reward.current_stream_redeems != int(value),
}

RedeemTrigger = event_triggers.EventTrigger[twitchio.ChannelPointsRedemptionAdd]
    
class ActionRedeemTrigger(event_triggers.ActionEventTrigger[twitchio.ChannelPointsRedemptionAdd]):
    TYPE_NAME = "twitch_redeem"
    def create_bot_script_context(self, bot, event):
        return tti.BotScriptContext(bot, redeem=event)

class CallbackRedeemTrigger(event_triggers.CallbackEventTrigger[twitchio.ChannelPointsRedemptionAdd]):
    pass
    

callback_redeem_triggers:dict[str, CallbackRedeemTrigger] = {}

merge_redeem_triggers = actions.create_triggers_merge_function(RedeemTrigger, ActionRedeemTrigger, callback_redeem_triggers)
