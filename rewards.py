import actions
from tronix import script, utils
import tronix_twitch_integrations as tti
import twitchio
from twitchio.ext import commands
from typing import Callable

IDEN_TYPE_ID = "id"
IDEN_TYPE_TITLE = "title"

RewardHandlerCallback = Callable[[commands.Bot, twitchio.ChannelPointsRedemptionAdd]]

class RewardIdentifier:
    def __init__(self, value:str, type:str=IDEN_TYPE_TITLE):
        self.value = value
        self.type = type
    
    def matches(self, payload:twitchio.ChannelPointsRedemptionAdd):
        if self.type == IDEN_TYPE_TITLE:
            return self.value == payload.reward.title
        elif self.type == IDEN_TYPE_ID:
            return self.value == payload.reward.id

class RewardHandler:
    def __init__(self, identifier:RewardIdentifier):
        self.identifier = identifier

    def handle(self, bot:commands.Bot, payload:twitchio.ChannelPointsRedemptionAdd):
        raise NotImplementedError
    
class ActionRewardHandler(RewardHandler):
    def __init__(self, identifier:RewardIdentifier, action_name:str, action_mapping:actions.RewardActionValueMapping|None=None):
        super().__init__(identifier)
        self.action_name = action_name
        self.action_mapping = action_mapping

    def handle(self, bot:commands.Bot, payload:twitchio.ChannelPointsRedemptionAdd):
        action = actions.action_table.get(self.action_name, None)
        if action is None:
            ... #TODO exception unknown action
        script_scope = {"twitch_context": script.ScriptVariable(utils.wrap_python_value(tti.BotScriptContext(bot, redeem_payload=payload)))}
        if self.action_mapping is not None:
            filled_values = self.action_mapping.fill_values(payload.user_input)
            script_scope.update(action.collect_script_values(filled_values))
        s = script.Script(action.script, script_scope)
        return actions.script_runner.run_async(s)
    

class CallbackRewardHandler(RewardHandler):
    @staticmethod
    def create(identifier:RewardIdentifier):
        def decor(callback:RewardHandlerCallback):
            return CallbackRewardHandler(identifier, callback)
        return decor
    
    @staticmethod
    def new(identifier:RewardIdentifier, callback:RewardHandlerCallback):
        return CallbackRewardHandler(identifier, callback)
    
    def __init__(self, identifier:RewardIdentifier, callback:RewardHandlerCallback, bind=None):
        self.identifier = identifier
        self.callback = callback
        self.bind = bind

    def handle(self, bot:commands.Bot, payload:twitchio.ChannelPointsRedemptionAdd):
        if self.bind is None:
            cb = self.callback
        else:
            cb = self.callback.__get__(self.bind, type(self.bind))
        return cb(bot, payload)
    
    def __call__(self, bot:commands.Bot, payload:twitchio.ChannelPointsRedemptionAdd):
        return self.handle(bot, payload)