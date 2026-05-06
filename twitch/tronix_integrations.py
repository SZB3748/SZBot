from . import analytics
from datetime import datetime, timedelta, timezone
from tronix import builtins, exceptions, script, utils
from tronix.script import ScriptVariable
from tronix.utils import ScriptFunction
import twitchio
from twitchio.ext import commands
from typing import Self
from uuid import UUID

TWITCH_CONTEXT_VAR_NAME = "twitch_context"

_COLOR_NAMES = {"color","colour"}

class InvalidTwitchContext(exceptions.TRuntimeException):
    "Twitch context is not of the expected type."

class BotScriptContext:
    def __init__(self, bot:commands.Bot, command_ctx:commands.Context|None=None, redeem_payload:twitchio.ChannelPointsRedemptionAdd|None=None, message:twitchio.ChatMessage|None=None):
        self.bot = bot
        self.command_ctx = command_ctx
        self.redeem_payload = redeem_payload
        self.message = message

    def resolve_broadcaster(self)->twitchio.PartialUser|None:
        if self.message is not None:
            return self.message.broadcaster
        elif self.command_ctx is not None:
            return self.command_ctx.broadcaster
        elif self.redeem_payload is not None:
            return self.redeem_payload.broadcaster

    def resolve_author(self)->twitchio.PartialUser|None:
        if self.message is not None:
            return self.message.chatter
        elif self.command_ctx is not None:
            return self.command_ctx.chatter
        elif self.redeem_payload is not None:
            return self.redeem_payload.user

    def resolve_message(self)->twitchio.ChatMessage|None:
        if self.message is not None:
            return self.message
        elif self.command_ctx is not None:
            return self.command_ctx.message
        
def _resolve_broadcaster(tctx:BotScriptContext):
    b = tctx.resolve_broadcaster()
    if b is None:
        ... #TODO error missing context to auto-determine broadcaster
    return b

def _resolve_author(tctx:BotScriptContext):
    u = tctx.resolve_author()
    if u is None:
        ... #TODO error missing context to auto-determine author/initiator
    return u

def _resolve_message(tctx:BotScriptContext):
    msg = tctx.resolve_message()
    if msg is None:
        ... #TODO error missing context to auto-determine message
    return msg

class analytics_window(builtins._pair[datetime|None, datetime|None]):
    
    def __init__(self, first, second):
        super().__init__(first, second)
        self.__origin = datetime.now(timezone.utc)

    @property
    def is_empty(self):
        return self._pair[0] is None and self._pair[1] is None
    
    @property
    def is_start_open(self):
        return self._pair[0] is None
    
    @property
    def is_end_open(self):
        return self._pair[1] is None
    
    @property
    def age(self):
        return (datetime.now() - self.__origin).total_seconds()


class _AnalyticsWindowType(builtins._PairType):
    f_construct:ScriptFunction[Self] = ScriptFunction()
    construct = f_construct

class _CommandContextType(script.ScriptDataType[commands.Context]):
    def getattr(self, obj, name):
        if name == "author":
            return script.wrap_python_value(obj.inner.author)
        elif name == "broadcaster":
            return script.wrap_python_value(obj.inner.broadcaster)
        elif name == "command":
            ... #TODO command type
        else:
            raise AttributeError(repr(name))
    
    def setattr(self, obj, name, value):
        raise TypeError(f"{self.name} object is read-only")
        
    def delattr(self, obj, name):
        raise TypeError(f"{self.name} object is read-only")

class _RedeemContextType(script.ScriptDataType[twitchio.ChannelPointsRedemptionAdd]):
    def getattr(self, obj, name):
        if name == "broadcaster":
            return script.wrap_python_value(obj.inner.broadcaster)
        elif name == "id":
            return script.wrap_python_value(UUID(obj.inner.id))
        elif name == "redeemed_at":
            return script.wrap_python_value(obj.inner.redeemed_at)
        elif name == "reward":
            ... #TODO reward type
        elif name == "status":
            return script.wrap_python_value(obj.inner.status)
        elif name == "user":
            return script.wrap_python_value(obj.inner.user)
        elif name == "user_input":
            return script.wrap_python_value(obj.inner.user_input)
        else:
            raise AttributeError(repr(name))
    
    def setattr(self, obj, name, value):
        raise TypeError(f"{self.name} object is read-only")
        
    def delattr(self, obj, name):
        raise TypeError(f"{self.name} object is read-only")

class _TwitchUserType(script.ScriptDataType[twitchio.PartialUser]):
    def getattr(self, obj, name):
        if name == "id":
            return script.wrap_python_value(int(obj.inner.id))
        elif name == "display_name":
            return script.wrap_python_value(obj.inner.display_name)
        elif name == "mention":
            return script.wrap_python_value(obj.inner.mention)
        elif name == "name":
            return script.wrap_python_value(obj.inner.name)
        else:
            raise AttributeError(repr(name))
    
    def setattr(self, obj, name, value):
        raise TypeError(f"{self.name} object is read-only")
        
    def delattr(self, obj, name):
        raise TypeError(f"{self.name} object is read-only")
    
class _TwitchChatterType(script.ScriptDataType[twitchio.Chatter]):
    def getattr(self, obj, name):
        if name == "broadcaster":
            return script.wrap_python_value(obj.inner.channel)
        elif name == "is_staff":
            return script.wrap_python_value(obj.inner.staff)
        elif name == "is_admin":
            return script.wrap_python_value(obj.inner.admin)
        elif name == "is_broadcaster":
            return script.wrap_python_value(obj.inner.broadcaster)
        elif name == "is_moderator":
            return script.wrap_python_value(obj.inner.moderator)
        elif name == "is_vip":
            return script.wrap_python_value(obj.inner.vip)
        elif name == "is_artist":
            return script.wrap_python_value(obj.inner.artist)
        elif name == "is_founder":
            return script.wrap_python_value(obj.inner.founder)
        elif name == "is_subscriber":
            return script.wrap_python_value(obj.inner.subscriber)
        elif name == "is_no_audio":
            return script.wrap_python_value(obj.inner.no_audio)
        elif name == "is_no_video":
            return script.wrap_python_value(obj.inner.no_video)
        elif name == "is_partner":
            return script.wrap_python_value(bool(getattr(obj.inner, "_is_verified", False)))
        elif name == "is_turbo":
            return script.wrap_python_value(obj.inner.turbo)
        elif name == "is_prime":
            return script.wrap_python_value(obj.inner.prime)
        elif name in _COLOR_NAMES:
            return script.wrap_python_value(list(obj.inner.colour.rgb_coords))
        else:
            return self.parent.getattr(obj, name)
    
    def setattr(self, obj, name, value):
        raise TypeError(f"{self.name} object is read-only")
        
    def delattr(self, obj, name):
        raise TypeError(f"{self.name} object is read-only")

class _TwitchMessageType(script.ScriptDataType[twitchio.ChatMessage]):
    def getattr(self, obj, name):
        if name == "broadcaster":
            return script.wrap_python_value(obj.inner.broadcaster)
        elif name == "author":
            return script.wrap_python_value(obj.inner.chatter)
        elif name == "id":
            return script.wrap_python_value(UUID(obj.inner.id))
        elif name == "text":
            return script.wrap_python_value(obj.inner.text)
        elif name == "reply":
            return script.wrap_python_value(obj.inner.reply) #TODO chat message reply type
        elif name == "type":
            return script.wrap_python_value(obj.inner.type)
        elif name in _COLOR_NAMES:
            return script.wrap_python_value(obj.inner.colour)
        else:
            raise AttributeError(repr(name))
    
    def setattr(self, obj, name, value):
        raise TypeError(f"{self.name} object is read-only")
        
    def delattr(self, obj, name):
        raise TypeError(f"{self.name} object is read-only")

class _TwitchContextType(script.ScriptDataType[BotScriptContext]):
    def getattr(self, obj, name):
        if name == "command":
            return script.wrap_python_value(obj.inner.command_ctx)
        elif name == "redeem":
            return script.wrap_python_value(obj.inner.redeem_payload)
        elif name == "message":
            return script.wrap_python_value(obj.inner.message)
        else:
            raise AttributeError(repr(name))
    
    def setattr(self, obj, name, value):
        raise TypeError(f"{self.name} object is read-only")
        
    def delattr(self, obj, name):
        raise TypeError(f"{self.name} object is read-only")
        

TwitchUser = _TwitchUserType("TwitchUser", twitchio.PartialUser, script.BASE_TYPE)
TwitchChatter = _TwitchChatterType("TwitchChatter", twitchio.Chatter, TwitchUser)
TwitchMessage = _TwitchMessageType("TwitchMessage", twitchio.ChatMessage, script.BASE_TYPE)
CommandContext = _CommandContextType("CommandContext", commands.Context, script.BASE_TYPE)
RedeemContext = _RedeemContextType("RedeemContext", twitchio.ChannelPointsRedemptionAdd, script.BASE_TYPE)
TwitchContext = _TwitchContextType("TwitchContext", BotScriptContext, script.BASE_TYPE)

AnalyticsWindow = _AnalyticsWindowType("AnalyticsWindow", analytics_window, builtins.Pair)

def _get_tctx(ctx:script.ScriptContext):
    ns = ctx.stack.find_name(TWITCH_CONTEXT_VAR_NAME)
    if ns is None:
        raise exceptions.TMissingName(f"missing twitch context {repr(TWITCH_CONTEXT_VAR_NAME)}")
    tctxv:script.ScriptValue[BotScriptContext] = ns[TWITCH_CONTEXT_VAR_NAME].get()
    if not tctxv.type.issubtype(TwitchContext):
        raise InvalidTwitchContext("twitch context is missing or was overriden")
    return tctxv.inner

async def _resolve_user(tctx:BotScriptContext, dest:ScriptVariable[str|int|twitchio.PartialUser])->twitchio.User|None:
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

_UserUnion = [builtins.String, builtins.Integer, TwitchUser]

@_AnalyticsWindowType.f_construct.overload(("first", ["datetime",builtins.NullType]), ("second", ["datetime",builtins.NullType]))
def AnalyticsWindow_construct(self, first:ScriptVariable[datetime], second:ScriptVariable[datetime]):
    return ScriptVariable(self, analytics_window(first, second))

f_twitch_send_message = ScriptFunction()
f_twitch_shoutout = ScriptFunction()
f_twitch_timeout = ScriptFunction()
f_twitch_ban = ScriptFunction()
f_twitch_unban = ScriptFunction()
f_twitch_current_stream_window = ScriptFunction()
f_twitch_is_this_user_first_message = ScriptFunction()
f_twitch_is_this_channel_first_message = ScriptFunction()

@f_twitch_send_message.overload(("msg", builtins.String), pass_ctx=True)
async def twitch_send_message_autodest(ctx:script.ScriptContext, msg:ScriptVariable[str]):
    tctx = _get_tctx(ctx)
    await _resolve_broadcaster(tctx).send_message(msg.get().inner, tctx.bot.user)

@f_twitch_send_message.overload(("msg", builtins.String), ("broadcaster", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def twitch_send_message_manualdest(ctx:script.ScriptContext, msg:ScriptVariable[str], broadcaster:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = _get_tctx(ctx)
    if broadcaster.get().inner is None:
        b = _resolve_broadcaster(tctx)
    else:
        b = await _resolve_user(tctx, broadcaster)
        if b is None:
            ... #TODO error could not resolve broadcaster
    await b.send_message(msg.get().inner, sender=tctx.bot.user)

@f_twitch_shoutout.overload(("user", _UserUnion), pass_ctx=True)
async def twitch_shoutout_autodest(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser]):
    tctx = _get_tctx(ctx)
    await _resolve_broadcaster(tctx).send_shoutout(to_broadcaster=user.get().inner, moderator=tctx.bot.user)

@f_twitch_shoutout.overload(("user", _UserUnion), ("broadcaster", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def twitch_shoutout_manualdest(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser], broadcaster:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = _get_tctx(ctx)
    if broadcaster.get().inner is None:
        b = _resolve_broadcaster(tctx)
    else:
        b = await _resolve_user(tctx, broadcaster)
        if b is None:
            ... #TODO error could not resolve broadcaster
    await b.send_shoutout(to_broadcaster=user, moderator=tctx.bot.user)

@f_twitch_timeout.overload(("user", _UserUnion), ("duration", [builtins.Integer, builtins.Float], 600), ("reason", [builtins.String, builtins.NullType], None), ("broadcaster", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def twitch_timeout(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser], duration:ScriptVariable[int|float], reason:ScriptVariable[str|None], broadcaster:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = _get_tctx(ctx)
    if broadcaster.get().inner is None:
        b = _resolve_broadcaster(tctx)
    else:
        b = await _resolve_user(tctx, broadcaster)
        if b is None:
            ... #TODO error could not resolve broadcaster
    
    await b.timeout_user(user=user.get().inner, duration=duration.get().inner, reason=reason.get().inner, moderator=tctx.bot.user)

@f_twitch_ban.overload(("user", _UserUnion), ("reason", [builtins.String, builtins.NullType], None), ("broadcaster", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def twitch_ban(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser], reason:ScriptVariable[str|None], broadcaster:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = _get_tctx(ctx)
    if broadcaster.get().inner is None:
        b = _resolve_user(tctx)
    else:
        b = await _resolve_user(tctx, broadcaster)
        if b is None:
            ... #TODO error could not resolve dest
    
    await b.ban_user(user=user.get().inner, reason=reason.get().inner, moderator=tctx.bot.user)

@f_twitch_unban.overload(("user", _UserUnion), pass_ctx=True)
async def twitch_unban_autodest(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser]):
    tctx = _get_tctx(ctx)
    await _resolve_broadcaster(tctx).unban_user(user_id=user.get().inner, moderator=tctx.bot.user)

@f_twitch_unban.overload(("user", _UserUnion), ("broadcaster", _UserUnion), pass_ctx=True)
async def twitch_unban_manualdest(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser], broadcaster:ScriptVariable[str|int|twitchio.PartialUser]):
    tctx = _get_tctx(ctx)
    b = await _resolve_user(tctx, broadcaster)
    if b is None:
        ... #TODO error could not resolve broadcaster
    
    await b.unban_user(user_id=user.get().inner, moderator=tctx.bot.user)

async def _query_current_stream_window(broadcaster_id:int, seconds:int|float, error:int|float):
    starts = analytics.StreamStartStat
    ends = analytics.StreamEndStat

    executed = await analytics.execute_statement_async(f"SELECT MAX({ends.COLUMN_HAPPENED}) FROM {ends.TABLE_NAME} WHERE {ends.COLUMN_BROADCASTER_ID}=?", broadcaster_id, query_count=1)
    if executed.result[0] is None:
        executed = await analytics.execute_statement_async(f"SELECT MAX({starts.COLUMN_HAPPENED}) AS \"{starts.COLUMN_HAPPENED} [DATETIME]\" FROM {starts.TABLE_NAME} WHERE {starts.COLUMN_BROADCASTER_ID}=?", broadcaster_id, query_count=1)
    else:
        last_end = executed.result[0]
        executed = await analytics.execute_statement_async(
            f"SELECT {starts.COLUMN_HAPPENED} FROM {starts.TABLE_NAME} WHERE {starts.COLUMN_BROADCASTER_ID}=? AND (? - {starts.COLUMN_HAPPENED}) <= ? ORDER BY {starts.COLUMN_HAPPENED}",
            broadcaster_id, last_end, seconds, query_count=1
        )
    return script.wrap_python_value(analytics_window(None if executed.result is None else datetime.fromtimestamp(executed.result[0], timezone.utc)-timedelta(seconds=error), None))

@f_twitch_current_stream_window.overload(("broadcaster", _UserUnion+[builtins.NullType], None), ("threshold_secs", [builtins.Integer,builtins.Float], 0), ("threshold_mins", [builtins.Integer,builtins.Float], 0), ("threshold_hours", [builtins.Integer,builtins.Float], 0), ("error", [builtins.Integer,builtins.Float], 2.5), pass_ctx=True)
async def twitch_current_stream_window(ctx:script.ScriptContext, broadcaster:ScriptVariable[str|int|twitchio.PartialUser|None], threshold_secs:ScriptVariable[int|float], threshold_mins:ScriptVariable[int|float], threshold_hours:ScriptVariable[int|float], error:ScriptVariable[int|float]):
    tctx = _get_tctx(ctx)
    seconds = threshold_secs.get().inner + threshold_mins.get().inner * 60 + threshold_hours.get().inner * 3600
    if broadcaster.get().inner is None:
        b = _resolve_broadcaster(tctx)
    else:
        b = await _resolve_user(tctx, broadcaster)
        if b is None:
            ... #TODO error could not resolve broadcaster
    return await _query_current_stream_window(int(b.id), seconds, error.get().inner)

async def _is_first_message(window:ScriptVariable[analytics_window], msg:UUID, filter_parts:list[str], filter_values:list):
    msgs = analytics.MessageStat
    aw = window.get().inner
    if not aw.is_empty:
        if not aw.is_start_open:
            filter_parts.append(f"{msgs.COLUMN_HAPPENED} >= ?")
            filter_values.append(aw.first)
        if not aw.is_end_open:
            filter_parts.append(f"{msgs.COLUMN_HAPPENED} <= ?")
            filter_values.append(aw.second)

    executed = await analytics.execute_statement_async(f"SELECT message_id FROM {msgs.TABLE_NAME} WHERE {(" AND ".join(filter_parts))} ORDER BY happened ASC", *filter_values, query_count=1)
    print(executed.result, msg)
    if executed.result is None or executed.result[0] != msg:
        return builtins.false
    else:
        return builtins.true

@f_twitch_is_this_user_first_message.overload(("window", AnalyticsWindow), ("message", [builtins.UUID,TwitchMessage,builtins.NullType], None), ("author", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def twitch_is_this_user_first_message(ctx:script.ScriptContext, window:ScriptVariable[analytics_window], message:ScriptVariable[UUID|twitchio.ChatMessage|None], author:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = _get_tctx(ctx)
    msg = message.get()
    user = author.get()
    uid:int|None = None

    if msg.inner is None:
        m = _resolve_message(tctx)
        if user.inner is None:
            uid = int(m.chatter.id)
        msg = UUID(m.id)
    elif msg.type.issubtype(builtins.UUID):
        if user.inner is None:
            ... #TODO error could not resolve message author
        msg = msg.inner
    else:
        if user.inner is None:
            uid = int(msg.chatter.id)
        msg = UUID(msg.id)

    if uid is None:
        u = await _resolve_user(tctx, author)
        if u is None:
            ... #TODO error could not resolve provided author
        uid = int(u.id)
    
    return await _is_first_message(window, msg, [f"{analytics.MessageStat.COLUMN_AUTHOR_ID}=?"], [uid])
    

@f_twitch_is_this_channel_first_message.overload(("window", AnalyticsWindow), ("message", [builtins.UUID,TwitchMessage,builtins.NullType], None), pass_ctx=True)
async def twitch_is_this_channel_first_message(ctx:script.ScriptContext, window:ScriptVariable[analytics_window], message:ScriptVariable[UUID|twitchio.ChatMessage|None]):
    tctx = _get_tctx(ctx)
    msg = message.get()

    if msg.inner is None:
        msg = UUID(_resolve_message(tctx).id)
    elif msg.type.issubtype(builtins.UUID):
        msg = msg.inner
    else:
        msg = UUID(msg.id)
    
    return await _is_first_message(window, msg, [], [])


def activate():
    utils.add_type(TwitchUser, constructor=False)
    script.DATA_TYPE_TABLE[twitchio.User] = TwitchUser #type alias
    utils.add_type(TwitchChatter, constructor=False)
    utils.add_type(TwitchMessage, constructor=False)
    utils.add_type(CommandContext, constructor=False)
    utils.add_type(RedeemContext, constructor=False)
    utils.add_type(TwitchContext, constructor=False)
    utils.add_type(AnalyticsWindow)
    script.SCRIPT_FUNCTION_TABLE["twitch_send_message"] = f_twitch_send_message
    script.SCRIPT_FUNCTION_TABLE["twitch_shoutout"] = f_twitch_shoutout
    script.SCRIPT_FUNCTION_TABLE["twitch_timeout"] = f_twitch_timeout
    script.SCRIPT_FUNCTION_TABLE["twitch_ban"] = f_twitch_ban
    script.SCRIPT_FUNCTION_TABLE["twitch_unban"] = f_twitch_unban
    script.SCRIPT_FUNCTION_TABLE["twitch_current_stream_window"] = f_twitch_current_stream_window
    script.SCRIPT_FUNCTION_TABLE["twitch_is_this_user_first_message"] = f_twitch_is_this_user_first_message
    script.SCRIPT_FUNCTION_TABLE["twitch_is_this_channel_first_message"] = f_twitch_is_this_channel_first_message