import tronix
from tronix import exceptions, script, script_builtins, utils
import twitchio
from twitchio.ext import commands

TWITCH_CONTEXT_VAR_NAME = "twitch_context"

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

async def twitch_send_message(ctx:script.ScriptContext):
    ns = ctx.stack.find_name(TWITCH_CONTEXT_VAR_NAME)
    if ns is None:
        ... #TODO error no twitch context
    tctxv:script.ScriptValue[BotScriptContext] = ns[TWITCH_CONTEXT_VAR_NAME].get()
    if not tctxv.type.issubtype(TwitchContext):
        ... #TODO error invalid twitch context
    tctx = tctxv.inner
    
    pc = len(ctx.params)
    if pc < 1:
        ... #TODO error
    elif pc > 2:
        ... #TODO error
    
    msg:script.ScriptValue[str] = ctx.params[0].get()
    if not msg.type.issubtype(script_builtins.String):
        ... #TODO error type

    if pc == 1:
        if tctx.command_ctx is not None:
            await tctx.command_ctx.send(msg.inner)
        elif tctx.redeem_payload is not None:
            await tctx.redeem_payload.broadcaster.send_message(msg.inner, tctx.bot.user)
        else:
            ... #TODO error missing context to auto-determine message destination
    else: #pc == 2
        dest = ctx.params[1].get()
        if dest.type.issubtype(script_builtins.String):
            if dest.inner.isdigit():
                destuser = await tctx.bot.fetch_user(id=dest.inner)
            else:
                destuser = await tctx.bot.fetch_user(login=dest.inner)
        elif dest.type.issubtype(script_builtins.Integer):
            destuser = await tctx.bot.fetch_user(id=dest.inner)
        elif isinstance(dest.inner, twitchio.User, twitchio.PartialUser):
            destuser = dest.inner
        else:
            ... #TODO error type
        await destuser.send_message(msg.inner, tctx.bot.user)

def activate():
    utils.add_type(CommandContext, constructor=False)
    utils.add_type(RedeemContext, constructor=False)
    utils.add_type(TwitchContext, constructor=False)
    script.SCRIPT_FUNCTION_TABLE["twitch_send_message"] = twitch_send_message