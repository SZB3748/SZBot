from tronix import builtins, exceptions, script, utils
from tronix.script import ScriptVariable
from tronix.utils import ScriptFunction, ScriptFunctionParam
import twitchio
from twitchio.ext import commands

TWITCH_CONTEXT_VAR_NAME = "twitch_context"

class InvalidTwitchContext(exceptions.TRuntimeException):
    "Twitch context is not of the expected type."

class BotScriptContext:
    def __init__(self, bot:commands.Bot, command_ctx:commands.Context|None=None, redeem_payload:twitchio.ChannelPointsRedemptionAdd|None=None):
        self.bot = bot
        self.command_ctx = command_ctx
        self.redeem_payload = redeem_payload

class _CommandContextType(script.ScriptDataType):
    ...

class _RedeemContextType(script.ScriptDataType):
    ...

class _TwitchUserType(script.ScriptDataType):
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
        


TwitchUser = _TwitchUserType("TwitchUser", twitchio.PartialUser, script.BASE_TYPE)
CommandContext = _CommandContextType("CommandContext", commands.Context, script.BASE_TYPE)
RedeemContext = _RedeemContextType("RedeemContext", twitchio.ChannelPointsRedemptionAdd, script.BASE_TYPE)
TwitchContext = _TwitchContextType("TwitchContext", BotScriptContext, script.BASE_TYPE)

def _get_tctx(ctx:script.ScriptContext):
    ns = ctx.stack.find_name(TWITCH_CONTEXT_VAR_NAME)
    if ns is None:
        raise exceptions.TMissingName(f"missing twitch context {repr(TWITCH_CONTEXT_VAR_NAME)}")
    tctxv:script.ScriptValue[BotScriptContext] = ns[TWITCH_CONTEXT_VAR_NAME].get()
    if not tctxv.type.issubtype(TwitchContext):
        raise InvalidTwitchContext("twitch context is missing or was overriden")
    return tctxv.inner

async def _resolve_destuser(tctx:BotScriptContext, dest:ScriptVariable[str|int|twitchio.PartialUser]):
    d = dest.get()
    if d.type.issubtype(builtins.String):
        if d.inner.isdigit():
            destuser = await tctx.bot.fetch_user(id=d.inner)
        else:
            destuser = await tctx.bot.fetch_user(login=d.inner)
    elif d.type.issubtype(builtins.Integer):
        destuser = await tctx.bot.fetch_user(id=d.inner)
    else:
        destuser = d.inner
    return destuser

f_twitch_send_message = ScriptFunction()
f_twitch_shoutout = ScriptFunction()
f_twitch_timeout = ScriptFunction()
f_twitch_ban = ScriptFunction()

@f_twitch_send_message.overload(ScriptFunctionParam("msg", [builtins.String]), pass_ctx=True)
async def twitch_send_message_autodest(ctx:script.ScriptContext, msg:ScriptVariable[str]):
    tctx = _get_tctx(ctx)
    if tctx.command_ctx is not None:
        await tctx.command_ctx.send(msg.get().inner)
    elif tctx.redeem_payload is not None:
        await tctx.redeem_payload.broadcaster.send_message(msg.get().inner, tctx.bot.user)
    else:
        ... #TODO error missing context to auto-determine message destination

@f_twitch_send_message.overload(ScriptFunctionParam("msg", [builtins.String]), ScriptFunctionParam("dest", [builtins.String, builtins.Integer, TwitchUser]), pass_ctx=True)
async def twitch_send_message_manualdest(ctx:script.ScriptContext, msg:ScriptVariable[str], dest:ScriptVariable[str|int|twitchio.PartialUser]):
    tctx = _get_tctx(ctx)
    destuser = await _resolve_destuser(tctx, dest)
    await destuser.send_message(msg.get().inner, tctx.bot.user)

@f_twitch_shoutout.overload(ScriptFunctionParam("user", [builtins.String, builtins.Integer, TwitchUser]), pass_ctx=True)
async def twitch_shoutout_autodest(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser]):
    tctx = _get_tctx(ctx)
    if tctx.command_ctx is not None:
        await tctx.command_ctx.broadcaster.send_shoutout(to_broadcaster=user)
    elif tctx.redeem_payload is not None:
        await tctx.redeem_payload.broadcaster.send_shoutout(to_broadcaster=user)
    else:
        ... #TODO error missing context to auto-determine message destination

@f_twitch_shoutout.overload(ScriptFunctionParam("user", [builtins.String, builtins.Integer, TwitchUser]), ScriptFunctionParam("dest", [builtins.String, builtins.Integer, TwitchUser]), pass_ctx=True)
async def twitch_shoutout_manualdest(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser], dest:ScriptVariable[str|int|twitchio.PartialUser]):
    tctx = _get_tctx(ctx)
    destuser = await _resolve_destuser(tctx, dest)
    await destuser.send_shoutout(to_broadcaster=user)


def activate():
    utils.add_type(TwitchUser, constructor=False)
    utils.add_type(CommandContext, constructor=False)
    utils.add_type(RedeemContext, constructor=False)
    utils.add_type(TwitchContext, constructor=False)
    script.SCRIPT_FUNCTION_TABLE["twitch_send_message"] = f_twitch_send_message
    script.SCRIPT_FUNCTION_TABLE["twitch_shoutout"] = f_twitch_shoutout