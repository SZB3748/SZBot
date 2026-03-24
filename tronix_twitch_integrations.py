import tronix
from tronix import exceptions, script, utils
import twitchio
from twitchio.ext import commands


class BotScriptContext:
    def __init__(self, bot:commands.Bot, command_ctx:commands.Context|None=None, redeem_payload:twitchio.ChannelPointsRedemptionAdd|None=None):
        self.bot = bot
        self.command_ctx = command_ctx
        self.redeem_payload = redeem_payload

class _CommandContextType(script.ScriptDataType):
    ...

class _RedeemContextType(script.ScriptDataType):
    ...

class _TwitchContextType(script.ScriptDataType):
    def getattr(self, obj:script.ScriptValue[BotScriptContext], name:str):
        if name == "command":
            return script.ScriptValue(CommandContext, obj.inner.command_ctx)
        elif name == "redeem":
            return script.ScriptValue(RedeemContext, obj.inner.redeem_payload)
        else:
            raise AttributeError(repr(name))
    
    def setattr(self, obj, name, value):
        raise TypeError(f"{self.name} object is read-only")
        
    def delattr(self, obj, name):
        raise TypeError(f"{self.name} object is read-only")
        


CommandContext = _CommandContextType("CommandContext", _CommandContextType, script.BASE_TYPE)
RedeemContext = _RedeemContextType("RedeemContext", _RedeemContextType, script.BASE_TYPE)
TwitchContext = _TwitchContextType("TwitchContext", _TwitchContextType, script.BASE_TYPE)