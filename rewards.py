import actions
import datafile
import json
import os
from tronix import script, utils
import tronix_twitch_integrations as tti
import twitchio
from twitchio.ext import commands
from typing import Any, Callable

IDEN_TYPE_ID = "id"
IDEN_TYPE_TITLE = "title"

REDEEM_HANDLERS_PATH = datafile.makepath("redeem_handlers.json")

RedeemHandlerCallback = Callable[[commands.Bot, twitchio.ChannelPointsRedemptionAdd], Any]

class RewardIdentifier:
    @staticmethod
    def from_str(s:str):
        return RewardIdentifier(*s.rsplit(";",1))

    def __init__(self, value:str, type:str=IDEN_TYPE_TITLE):
        self.value = value
        self.type = type
    
    def matches(self, payload:twitchio.ChannelPointsRedemptionAdd):
        if self.type == IDEN_TYPE_TITLE:
            return self.value == payload.reward.title
        elif self.type == IDEN_TYPE_ID:
            return self.value == payload.reward.id

    def __hash__(self):
        return hash((self.value, self.type))
    
    def __eq__(self, value):
        if isinstance(value, tuple):
            return value == (self.value, self.type)
        elif isinstance(value, RewardIdentifier):
            return value.type == self.type and value.value == self.value
        else:
            super().__eq__(value)

    def __str__(self):
        return f"{self.value};{self.type}"
    
    def __getstate__(self):
        return self.__dict__.copy()
    
    def __setstate__(self, d:dict[str]):
        self.__dict__.update(d)

RewardIdentifierKey = RewardIdentifier|tuple[str,str]

class RedeemHandler:
    def __init__(self, identifier:RewardIdentifier):
        self.identifier = identifier

    def handle(self, bot:commands.Bot, payload:twitchio.ChannelPointsRedemptionAdd):
        raise NotImplementedError
    
class ActionRedeemHandler(RedeemHandler):
    def __init__(self, identifier:RewardIdentifier, action_name:str, action_mapping:actions.RewardActionValueMapping|None=None):
        super().__init__(identifier)
        self.action_name = action_name
        self.action_mapping = action_mapping

    def __getstate__(self):
        return {
            "identifier": self.identifier.__getstate__(),
            "action_name": self.action_name,
            "action_mapping": self.action_mapping.__getstate__()
        }
    
    def __setstate__(self, d:dict[str]):
        identifier = RewardIdentifier.__new__(RewardIdentifier)
        action_mapping = actions.RewardActionValueMapping.__new__(actions.RewardActionValueMapping)
        identifier.__setstate__(d["identifier"])
        action_mapping.__setstate__(d["action_mapping"])

        self.action_name = str(d["action_name"])
        self.identifier = identifier
        self.action_mapping = action_mapping

    def handle(self, bot:commands.Bot, payload:twitchio.ChannelPointsRedemptionAdd):
        action = actions.load_action_table().get(self.action_name, None)
        if action is None:
            ... #TODO exception unknown action
        script_scope = {}
        if self.action_mapping is not None:
            filled_values = self.action_mapping.fill_values(payload.user_input)
            script_scope.update(action.collect_script_values(filled_values))
        s = script.Script(action.script, script_scope)
        if action.script_environment is None or actions.match_environment_name(action.script_environment, actions.current_environment_name):
            s.scope.setdefault(tti.TWITCH_CONTEXT_VAR_NAME, script.ScriptVariable(utils.wrap_python_value(tti.BotScriptContext(bot, redeem_payload=payload))))
            return actions.script_runner.run_async(s)
        else:
            uid, *_ = actions.enqueue_script(s, action.script_environment)
            async def _wait():
                await actions.wait_script_finish_async(uid)
            return _wait()
    

class CallbackRedeemHandler(RedeemHandler):
    @staticmethod
    def create(identifier:RewardIdentifier):
        def decor(callback:RedeemHandlerCallback):
            return CallbackRedeemHandler(identifier, callback)
        return decor
    
    @staticmethod
    def new(identifier:RewardIdentifier, callback:RedeemHandlerCallback):
        return CallbackRedeemHandler(identifier, callback)
    
    def __init__(self, identifier:RewardIdentifier, callback:RedeemHandlerCallback, bind=None):
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
    
def load_redeem_handlers(path:str=None)->dict[str,ActionRedeemHandler]:
    if path is None:
        path = REDEEM_HANDLERS_PATH
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        d:dict[str, dict[str]] = json.load(f)
    rtv = {}
    for k,v in d.items():
        rtv[RewardIdentifier.from_str(k)] = rh = ActionRedeemHandler.__new__(ActionRedeemHandler)
        rh.__setstate__(v)
    return rtv

def save_redeem_handlers(redeem_handlers:dict[str,ActionRedeemHandler], path:str=None):
    c = json.dumps({str(rh.identifier):rh.__getstate__() for rh in redeem_handlers.values() if isinstance(rh, ActionRedeemHandler)}, indent=4)
    with open(REDEEM_HANDLERS_PATH if path is None else path, "w") as f:
        f.write(c)
