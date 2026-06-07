from . import analytics
from datetime import datetime, timedelta, timezone
from tronix import builtins, exceptions, script, utils
from tronix.script import ScriptVariable
from tronix.utils import ScriptFunction
import twitchio
from twitchio.ext import commands
from typing import Any, Self
from uuid import UUID

TWITCH_CONTEXT_VAR_NAME = "twitch_context"

_COLOR_NAMES = {"color","colour"}

def _get_http():
    import twitchbot
    if twitchbot.bot is not None:
        return twitchbot.bot._http

class InvalidTwitchContext(exceptions.TRuntimeException):
    "Twitch context is not of the expected type."

class BotScriptContext:
    def __init__(self, bot:commands.Bot, command_ctx:commands.Context|None=None, redeem:twitchio.ChannelPointsRedemptionAdd|None=None, message:twitchio.ChatMessage|None=None,
                 cheer:twitchio.ChannelCheer|None=None, bitsuse:twitchio.ChannelBitsUse|None=None, follow:twitchio.ChannelFollow|None=None,
                 train_begin:twitchio.HypeTrainBegin|None=None, train_progress:twitchio.HypeTrainProgress|None=None, train_end:twitchio.HypeTrainEnd|None=None,
                 raid:twitchio.ChannelRaid|None=None, sub:twitchio.ChannelSubscribe|None=None, gift_sub:twitchio.ChannelSubscriptionGift|None=None,
                 sub_msg:twitchio.ChannelSubscriptionMessage|None=None):
        self.bot = bot
        self.command_ctx = command_ctx
        self.redeem = redeem
        self.message = message
        self.cheer = cheer
        self.bitsuse = bitsuse
        self.follow = follow
        self.train_begin = train_begin
        self.train_progress = train_progress
        self.train_end = train_end
        self.raid = raid
        self.sub = sub
        self.gift_sub = gift_sub
        self.sub_msg = sub_msg

    def resolve_broadcaster(self)->twitchio.PartialUser|None:
        if self.message is not None:
            return self.message.broadcaster
        elif self.command_ctx is not None:
            return self.command_ctx.broadcaster
        elif self.redeem is not None:
            return self.redeem.broadcaster

    def resolve_author(self)->twitchio.PartialUser|None:
        if self.message is not None:
            return self.message.chatter
        elif self.command_ctx is not None:
            return self.command_ctx.chatter
        elif self.redeem is not None:
            return self.redeem.user

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

def _resolve_redeem(tctx:BotScriptContext):
    if tctx.redeem is None:
        ... #TODO error missing redeem context
    return tctx.redeem

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


def _serialize_color(color:twitchio.Colour):
    return None if color is None else {k:getattr(color, k) for k in twitchio.Colour.__slots__}

def _deserialize_color(d):
    if isinstance(d, dict):
        colour = twitchio.Colour.__new__(twitchio.Colour)
        for name,val in d.items():
            setattr(colour, name, val)
        return colour
    else:
        return d

_AnalyticsWindowTypeAttrs = utils.ScriptAttributeHandler[analytics_window,Any](builtins._PairTypeAttrs)
@_AnalyticsWindowTypeAttrs.enforce_child_attrs()
@_AnalyticsWindowTypeAttrs.attach
class _AnalyticsWindowType(builtins._PairType):
    f_construct:ScriptFunction[Self] = ScriptFunction()
    construct = f_construct

    attrs = _AnalyticsWindowTypeAttrs
    attrs.alias(builtins._PairTypeAttrs["first"], "start")
    attrs.alias(builtins._PairTypeAttrs["second"], "end")
    attrs.entry("is_empty").readonly(utils.SimpleGetAttribute)
    attrs.entry("is_start_open").readonly(utils.SimpleGetAttribute)
    attrs.entry("is_end_open").readonly(utils.SimpleGetAttribute)
    attrs.entry("age").readonly(utils.SimpleGetAttribute)

_TwitchRewardTypeAttrs = utils.ScriptAttributeHandler[twitchio.ChannelPointsReward,Any](no_subscripting=True)
@_TwitchRewardTypeAttrs.enforce_child_attrs()
@_TwitchRewardTypeAttrs.attach
class _TwitchRewardType(script.ScriptDataType[twitchio.ChannelPointsReward]):
    def serialize(self, value, type_str=False):
        return dict(
            image=value.inner.image, broadcaster=utils.serialize_value_headless(value.inner.broadcaster, type_str=type_str),
            colour=_serialize_color(value.inner.colour), cooldown_until=value.inner.cooldown_until.isoformat(), cost=value.inner.cost,
            current_stream_redeems=value.inner.current_stream_redeems, default_image=value.inner.default_image,
            enabled=value.inner.enabled, id=value.inner.id, in_stock=value.inner.in_stock, input_required=value.inner.input_required,
            max_per_stream=value.inner.max_per_stream, max_per_user_per_stream=value.inner.max_per_user_per_stream,
            paused=value.inner.paused, prompt=value.inner.prompt, skip_queue=value.inner.skip_queue, title=value.inner.title
        )
    
    def deserialize(self, x:dict[str]):
        v = self.inner.__new__(self.inner)
        v._image = x["image"]
        v.broadcaster = TwitchUser.deserialize(x["broadcaster"])
        v.colour = _deserialize_color(x["colour"])
        v.cooldown_until = datetime.fromisoformat(x["cooldown_until"])
        v.cost = x["cost"]
        v.current_stream_redeems = x["current_stream_redeems"]
        v.default_image = x["default_image"]
        v.enabled = x["enabled"]
        v.id = x["id"]
        v.in_stock = x["in_stock"]
        v.input_required = x["input_required"]
        v.max_per_stream = None if (mps := x["max_per_stream"]) is None else twitchio.channel_points.RewardLimitSettings(*mps)
        v.max_per_user_per_stream = None if (mpups := x["max_per_user_per_stream"]) is None else twitchio.channel_points.RewardLimitSettings(*mpups)
        v.paused = twitchio.channel_points.RewardLimitSettings(*paused) if isinstance(paused := x["paused"], list) else paused
        v.prompt = x["prompt"]
        v.skip_queue = x["skip_queue"]
        v.title = x["title"]
        v._http = _get_http()
        return v

    attrs = _TwitchRewardTypeAttrs
    attrs.entry("broadcaster").readonly(utils.SimpleGetAttribute())
    attrs.entry("id").readonly(lambda o, n: script.wrap_python_value(UUID(o.inner.id)))
    attrs.entry("title").readonly(utils.SimpleGetAttribute())
    attrs.entry("cost").readonly(utils.SimpleGetAttribute())
    attrs.entry("prompt").readonly(utils.SimpleGetAttribute())
    attrs.entry("is_enabled").readonly(utils.SimpleGetAttribute("enabled"))
    attrs.entry("is_paused").readonly(utils.SimpleGetAttribute("paused"))
    attrs.entry("is_in_stock").readonly(utils.SimpleGetAttribute("in_stock"))
    attrs.entry("is_input_required").readonly(utils.SimpleGetAttribute("input_required"))
    attrs.entry("does_skip_queue").readonly(utils.SimpleGetAttribute("skip_queue"))
    attrs.entry(*_COLOR_NAMES).readonly(utils.SimpleGetAttribute())
    attrs.entry("cooldown_until").readonly(utils.SimpleGetAttribute())
    attrs.entry("max_per_stream").readonly(utils.SimpleGetAttribute())
    attrs.entry("max_per_user_per_stream").readonly(utils.SimpleGetAttribute())
    attrs.entry("global_cooldown").readonly(utils.SimpleGetAttribute())
    attrs.entry("default_image").readonly(lambda o, n: script.wrap_python_value(None if o.inner.default_image is None else builtins._rodict_dummy(o.inner.default_image)))
    attrs.entry("current_stream_redeems").readonly(utils.SimpleGetAttribute())

_TwitchRedeemTypeAttrs = utils.ScriptAttributeHandler[twitchio.ChannelPointsRedemptionAdd,Any](no_subscripting=True)
@_TwitchRedeemTypeAttrs.enforce_child_attrs()
@_TwitchRedeemTypeAttrs.attach
class _TwitchRedeemType(script.ScriptDataType[twitchio.ChannelPointsRedemptionAdd]):
    def serialize(self, value, type_str=False):
        return dict(
            broadcaster=utils.serialize_value_headless(value.inner.broadcaster, type_str=type_str), id=value.inner.id,
            redeemed_at=value.inner.redeemed_at.isoformat(), reward=utils.serialize_value_headless(value.inner.reward, type_str=type_str),
            status=value.inner.status, user=utils.serialize_value_headless(value.inner.user, type_str=type_str),
            user_input=value.inner.user_input
        )
    
    def deserialize(self, x):
        v = self.inner.__new__(self.inner)
        v.broadcaster = TwitchUser.deserialize(x["broadcaster"])
        v.id = x["id"]
        v.redeemed_at = datetime.fromisoformat(x["redeemed_at"])
        v.reward = TwitchReward.deserialize(x["reward"])
        v.status = x["status"]
        v.user = TwitchUser.deserialize(x["user"])
        v.user_input = x["user_input"]
        v._http = _get_http()
        return v
        
    attrs = _TwitchRedeemTypeAttrs
    attrs.entry("broadcaster").readonly(utils.SimpleGetAttribute())
    attrs.entry("id").readonly(lambda o,n: script.wrap_python_value(UUID(o.inner.id)))
    attrs.entry("redeemed_at").readonly(utils.SimpleGetAttribute())
    attrs.entry("reward").readonly(utils.SimpleGetAttribute())
    attrs.entry("status").readonly(utils.SimpleGetAttribute())
    attrs.entry("user").readonly(utils.SimpleGetAttribute())
    attrs.entry("user_input").readonly(utils.SimpleGetAttribute())

_TwitchCommandContextTypeAttrs = utils.ScriptAttributeHandler[commands.Context,Any](no_subscripting=True)
@_TwitchCommandContextTypeAttrs.enforce_child_attrs()
@_TwitchCommandContextTypeAttrs.attach
class _TwitchCommandContextType(script.ScriptDataType[commands.Context]):
    attrs = _TwitchCommandContextTypeAttrs
    attrs.entry("message").readonly(utils.SimpleGetAttribute())
    attrs.entry("invoked_with").readonly(utils.SimpleGetAttribute())
    attrs.entry("author").readonly(utils.SimpleGetAttribute())
    attrs.entry("broadcaster").readonly(utils.SimpleGetAttribute())
    attrs.entry("prefix").readonly(utils.SimpleGetAttribute())
    attrs.entry("is_valid").readonly(utils.MethodGetAttribute())
    #TODO attribute and type for command and bot

_TwitchAssetTypeAttrs = utils.ScriptAttributeHandler[twitchio.Asset,Any](no_subscripting=True)
@_TwitchAssetTypeAttrs.enforce_child_attrs()
@_TwitchAssetTypeAttrs.attach
class _TwitchAssetType(script.ScriptDataType[twitchio.Asset]):
    def serialize(self, value, type_str=False):
        return dict(
            dimensions=value.inner.dimensions, ext=value.inner._ext, name=value.inner._name,
            original_url=value.inner._original_url, url=value.inner._url
        )
    
    def deserialize(self, x):
        v = self.inner.__new__(self.inner)
        v._dimensions = x["dimensions"]
        v._ext = x["ext"]
        v._name = x["name"]
        v._original_url = x["original_url"]
        v._url = x["url"]
        v._http = _get_http()
        return v
    
    attrs = _TwitchAssetTypeAttrs
    attrs.entry("dimensions").readonly(lambda o, n: builtins.null if o.inner.dimensions is None else script.wrap_python_value(builtins._pair(*o.inner.dimensions)))
    attrs.entry("extension").readonly(utils.SimpleGetAttribute("ext"))
    attrs.entry("name").readonly(utils.SimpleGetAttribute("name"))
    attrs.entry("base_url").readonly(utils.SimpleGetAttribute("base_url"))
    attrs.entry("url").readonly(utils.SimpleGetAttribute("url"))

_TwitchUserTypeAttrs = utils.ScriptAttributeHandler[twitchio.PartialUser,Any](no_subscripting=True)
@_TwitchUserTypeAttrs.enforce_child_attrs()
@_TwitchUserTypeAttrs.attach
class _TwitchUserType(script.ScriptDataType[twitchio.PartialUser]):
    def serialize(self, value, type_str=False):
        return dict(id=value.inner.id, name=value.inner.name, display_name=value.inner.display_name)
    
    def deserialize(self, x:dict[str]):
        v = self.inner.__new__(self.inner)
        v.id = x["id"]
        v.name = x["name"]
        v.display_name = x["display_name"]
        v._http = _get_http()
        return v

    attrs = _TwitchUserTypeAttrs
    attrs.entry("id").readonly(lambda o, n: script.wrap_python_value(int(o.inner.id)))
    attrs.entry("display_name").readonly(utils.SimpleGetAttribute())
    attrs.entry("mention").readonly(utils.SimpleGetAttribute())
    attrs.entry("name").readonly(utils.SimpleGetAttribute())
    
_TwitchFullUserTypeAttrs = utils.ScriptAttributeHandler[twitchio.User,Any](_TwitchUserTypeAttrs, no_subscripting=True)
@_TwitchFullUserTypeAttrs.enforce_child_attrs()
@_TwitchFullUserTypeAttrs.attach
class _TwitchFullUserType(script.ScriptDataType[twitchio.User]):
    def serialize(self, value, type_str=False):
        d:dict[str] = self.parent.serialize(value, type_str=type_str)
        d.update(
            broadcaster_type=value.inner.broadcaster_type, created_at=value.inner.created_at.isoformat(),
            description=value.inner.description, email=value.inner.email,
            offline_image=utils.serialize_value_headless(value.inner.offline_image, type_str=type_str),
            profile_image=utils.serialize_value_headless(value.inner.profile_image, type_str=type_str),
            type=value.inner.type
        )
        return d

    def deserialize(self, x):
        v:twitchio.User = type(self.parent).deserialize(self, x)
        v.broadcaster_type = x["broadcaster_type"]
        v.created_at = datetime.fromisoformat(x["created_at"])
        v.description = x["description"]
        v.email = x["email"]
        v.offline_image = None if (oi := x["offline_image"]) is None else TwitchAsset.deserialize(oi)
        v.profile_image = TwitchAsset.deserialize(x["profile_image"])
        v.type = x["type"]
        return v

    attrs = _TwitchFullUserTypeAttrs
    attrs.entry("type").readonly(utils.SimpleGetAttribute())
    attrs.entry("broadcaster_type").readonly(utils.SimpleGetAttribute())
    attrs.entry("description").readonly(utils.SimpleGetAttribute())
    attrs.entry("profile_image").readonly(utils.SimpleGetAttribute())
    attrs.entry("offline_image").readonly(utils.SimpleGetAttribute())
    attrs.entry("email").readonly(utils.SimpleGetAttribute())
    attrs.entry("created_at").readonly(utils.SimpleGetAttribute())
    

_chatter_slots = {s for s in twitchio.Chatter.__slots__ if not s.startswith("__")}

_TwitchChatterTypeAttrs = utils.ScriptAttributeHandler[twitchio.Chatter,Any](_TwitchUserTypeAttrs, no_subscripting=True)
@_TwitchChatterTypeAttrs.enforce_child_attrs()
@_TwitchChatterTypeAttrs.attach
class _TwitchChatterType(script.ScriptDataType[twitchio.Chatter]):
    def serialize(self, value, type_str=False):
        d:dict[str] = self.parent.serialize(value)
        d.update(
            badges=[utils.serialize_value_headless(b, type_str=type_str) for b in value.inner._badges],
            channel=utils.serialize_value_headless(value.inner._channel, type_str=type_str),
            colour=_serialize_color(value.inner._colour)
        )
        return d
    
    def deserialize(self, x):
        v:twitchio.Chatter = type(self.parent).deserialize(self, x)
        v._badges = [TwitchMessageBadge.deserialize(b) for b in x["badges"]]
        v._channel = TwitchUser.deserialize(x["channel"])
        v._colour = _deserialize_color(x["colour"])
        for badge in v._badges:
            name = f"_is_{badge.set_id}".replace("-", "_")
            if name in _chatter_slots:
                setattr(v, name, True)
        
        return v
    
    attrs = _TwitchChatterTypeAttrs
    attrs.entry("broadcaster").readonly(utils.SimpleGetAttribute("channel"))
    attrs.entry("is_staff").readonly(utils.SimpleGetAttribute("staff"))
    attrs.entry("is_admin").readonly(utils.SimpleGetAttribute("admin"))
    attrs.entry("is_broadcaster").readonly(utils.SimpleGetAttribute("broadcaster"))
    attrs.entry("is_moderator").readonly(utils.SimpleGetAttribute("moderator"))
    attrs.entry("is_vip").readonly(utils.SimpleGetAttribute("vip"))
    attrs.entry("is_artist").readonly(utils.SimpleGetAttribute("artist"))
    attrs.entry("is_founder").readonly(utils.SimpleGetAttribute("founder"))
    attrs.entry("is_subscriber").readonly(utils.SimpleGetAttribute("subscriber"))
    attrs.entry("is_no_audio").readonly(utils.SimpleGetAttribute("no_audio"))
    attrs.entry("is_no_video").readonly(utils.SimpleGetAttribute("no_video"))
    attrs.entry("is_partner").readonly(lambda o, n: script.wrap_python_value(bool(getattr(o.inner, "_is_verified", False))))
    attrs.entry("is_turbo").readonly(utils.SimpleGetAttribute("turbo"))
    attrs.entry("is_prime").readonly(utils.SimpleGetAttribute("prime"))
    attrs.entry(*_COLOR_NAMES).readonly(lambda o, n: script.wrap_python_value(list(o.inner.colour.rgb_coords)))

_TwitchMessageBadgeTypeAttrs = utils.ScriptAttributeHandler[twitchio.ChatMessageBadge,Any](no_subscripting=True)
_TwitchMessageBadgeTypeAttrs.enforce_child_attrs()
_TwitchMessageBadgeTypeAttrs.attach
class _TwitchMessageBadgeType(script.ScriptDataType[twitchio.ChatMessageBadge]):
    def serialize(self, value, type_str=False):
        return dict(id=value.inner.id, info=value.inner.info, set_id=value.inner.set_id)
    
    def deserialize(self, x):
        v = self.inner.__new__(self.inner)
        v.id = x["id"]
        v.info = x["info"]
        v.set_id = x["set_id"]
        return v
    
    attrs = _TwitchMessageBadgeTypeAttrs
    attrs.entry("id").readonly(utils.SimpleGetAttribute())
    attrs.entry("set_id").readonly(utils.SimpleGetAttribute())
    attrs.entry("info").readonly(utils.SimpleGetAttribute())

_TwitchMessageCheerTypeAttrs = utils.ScriptAttributeHandler[twitchio.ChatMessageCheer,Any](no_subscripting=True)
@_TwitchMessageCheerTypeAttrs.enforce_child_attrs()
@_TwitchMessageCheerTypeAttrs.attach
class _TwitchMessageCheerType(script.ScriptDataType[twitchio.ChatMessageCheer]):
    def serialize(self, value, type_str=False):
        return dict(bits=value.inner.bits)
    
    def deserialize(self, x):
        v = self.inner.__new__(self.inner)
        v.bits = x["bits"]
        return v
    
    attrs = _TwitchMessageCheerTypeAttrs
    attrs.entry("bits").readonly(utils.SimpleGetAttribute())

_TwitchMessageReplyTypeAttrs = utils.ScriptAttributeHandler[twitchio.ChatMessageReply,Any](no_subscripting=True)
@_TwitchMessageReplyTypeAttrs.enforce_child_attrs()
@_TwitchMessageReplyTypeAttrs.attach
class _TwitchMessageReplyType(script.ScriptDataType[twitchio.ChatMessageReply]):
    def serialize(self, value, type_str=False):
        return dict(
            parent_message_body=value.inner.parent_message_body, parent_message_id=value.inner.parent_message_id,
            parent_user=utils.serialize_value_headless(value.inner.parent_user, type_str=type_str), thread_message_id=value.inner.thread_message_id,
            thread_user=utils.serialize_value_headless(value.inner.thread_user, type_str=type_str),
        )
    
    def deserialize(self, x):
        v = self.inner.__new__(self.inner)
        v.parent_message_body = x["parent_message_body"]
        v.parent_message_id = x["parent_message_id"]
        v.parent_user = TwitchUser.deserialize(x["parent_user"])
        v.thread_message_id = x["thread_message_id"]
        v.thread_user = TwitchUser.deserialize(x["thread_user"])
        return v
    
    attrs = _TwitchMessageReplyTypeAttrs
    attrs.entry("parent_message_body").readonly(utils.SimpleGetAttribute())
    attrs.entry("parent_message_id").readonly(lambda o,n: script.wrap_python_value(UUID(o.inner.parent_message_id)))
    attrs.entry("parent_user").readonly(utils.SimpleGetAttribute())
    attrs.entry("thread_message_id").readonly(utils.SimpleGetAttribute())
    attrs.entry("thread_user").readonly(utils.SimpleGetAttribute())

_TwitchMessageCheermoteTypeAttrs = utils.ScriptAttributeHandler[twitchio.ChatMessageCheermote,Any](no_subscripting=True)
@_TwitchMessageCheermoteTypeAttrs.enforce_child_attrs()
@_TwitchMessageCheermoteTypeAttrs.attach
class _TwitchMessageCheermoteType(script.ScriptDataType[twitchio.ChatMessageCheermote]):
    def serialize(self, value, type_str=False):
        return dict(bits=value.inner.bits, prefix=value.inner.prefix, tier=value.inner.tier)
    
    def deserialize(self, x):
        v = self.inner.__new__(self.inner)
        v.bits = x["bits"]
        v.prefix = x["prefix"]
        v.tier = x["tier"]
        return v
    
    attrs = _TwitchMessageCheermoteTypeAttrs
    attrs.entry("bits").readonly(utils.SimpleGetAttribute())
    attrs.entry("prefix").readonly(utils.SimpleGetAttribute())
    attrs.entry("tier").readonly(utils.SimpleGetAttribute())

_TwitchMessageEmoteTypeAttrs = utils.ScriptAttributeHandler[twitchio.ChatMessageEmote,Any](no_subscripting=True)
@_TwitchMessageEmoteTypeAttrs.enforce_child_attrs()
@_TwitchMessageEmoteTypeAttrs.attach
class _TwitchMessageEmoteType(script.ScriptDataType[twitchio.ChatMessageEmote]):
    def serialize(self, value, type_str=False):
        return dict(
            format=value.inner.format, id=value.inner.id, owner=utils.serialize_value_headless(value.inner.owner, type_str=type_str),
            set_id=value.inner.set_id
        )
    
    def deserialize(self, x):
        v = self.inner.__new__(self.inner)
        v.format = x["format"]
        v.id = x["id"]
        v.owner = TwitchUser.deserialize(x["owner"])
        v.set_id = x["set_id"]
        v._http = _get_http()
        return v
    
    attrs = _TwitchMessageEmoteTypeAttrs
    attrs.entry("format").readonly(utils.SimpleGetAttribute())
    attrs.entry("id").readonly(utils.SimpleGetAttribute())
    attrs.entry("set_id").readonly(utils.SimpleGetAttribute())
    attrs.entry("owner").readonly(utils.SimpleGetAttribute())

_TwitchMessageFragmentTypeAttrs = utils.ScriptAttributeHandler[twitchio.ChatMessageFragment,Any](no_subscripting=True)
@_TwitchMessageFragmentTypeAttrs.enforce_child_attrs()
@_TwitchMessageFragmentTypeAttrs.attach
class _TwitchMessageFragmentType(script.ScriptDataType[twitchio.ChatMessageFragment]):
    def serialize(self, value, type_str=False):
        return dict(
            cheermote=utils.serialize_value_headless(value.inner.cheermote, type_str=type_str),
            emote=utils.serialize_value_headless(value.inner.emote, type_str=type_str),
            mention=utils.serialize_value_headless(value.inner.mention, type_str=type_str),
            text=value.inner.text, type=value.inner.type
        )
    
    def deserialize(self, x):
        v = self.inner.__new__(self.inner)
        v.cheermote = None if (cheermote:=x["cheermote"]) is None else TwitchMessageCheermote.deserialize(cheermote)
        v.emote = None if (emote:=x["emote"]) is None else TwitchMessageEmote.deserialize(emote)
        v.mention = None if (mention:=x["mention"]) is None else TwitchUser.deserialize(mention)
        v.text = x["text"]
        v.type = x["type"]
        return v
    
    attrs = _TwitchMessageFragmentTypeAttrs
    attrs.entry("cheermote").readonly(utils.SimpleGetAttribute())
    attrs.entry("emote").readonly(utils.SimpleGetAttribute())
    attrs.entry("mention").readonly(utils.SimpleGetAttribute())
    attrs.entry("text").readonly(utils.SimpleGetAttribute())

_TwitchMessageTypeAttrs = utils.ScriptAttributeHandler[twitchio.ChatMessage,Any](no_subscripting=True)
@_TwitchMessageTypeAttrs.enforce_child_attrs()
@_TwitchMessageTypeAttrs.attach
class _TwitchMessageType(script.ScriptDataType[twitchio.ChatMessage]):
    def serialize(self, value, type_str=False):
        return dict(
            broadcaster=utils.serialize_value_headless(value.inner.broadcaster, type_str=type_str),
            fragments=[utils.serialize_value_headless(f, type_str=type_str) for f in value.inner.fragments],
            id=value.inner.id, text=value.inner.text, badges=[utils.serialize_value_headless(b, type_str=type_str) for b in value.inner.badges],
            channel_points_animation_id=value.inner.channel_points_animation_id, channel_points_id=value.inner.channel_points_id,
            chatter=utils.serialize_value_headless(value.inner.chatter, type_str=type_str),
            cheer=utils.serialize_value_headless(value.inner.cheer, type_str=type_str),
            colour=_serialize_color(value.inner.colour),
            reply=utils.serialize_value_headless(value.inner.reply, type_str=type_str),
            source_badges=[utils.serialize_value_headless(b, type_str=type_str) for b in value.inner.source_badges],
            source_broadcaster=utils.serialize_value_headless(value.inner.source_broadcaster, type_str=type_str),
            type=value.inner.type
        )
    
    def deserialize(self, x:dict[str]):
        v = self.inner.__new__(self.inner)
        v.broadcaster = TwitchUser.deserialize(x["broadcaster"])
        v.fragments = [TwitchMessageFragment.deserialize(f) for f in x["fragments"]]
        v.id = x["id"]
        v.text = x["text"]
        v.badges = [TwitchMessageBadge.deserialize(b) for b in x["badges"]]
        v.channel_points_animation_id = x["channel_points_animation_id"]
        v.channel_points_id = x["channel_points_id"]
        v.chatter = TwitchChatter.deserialize(x["chatter"])
        v.cheer = None if (cheer:=x["cheer"]) is None else TwitchMessageCheer.deserialize(cheer)
        v.colour = _deserialize_color(x["colour"])
        v.reply = None if (reply:=x["reply"]) is None else TwitchMessageReply.deserialize(reply)
        v.source_badges = [TwitchMessageBadge.deserialize(b) for b in x["source_badges"]]
        v.source_broadcaster = None if (sb:=x["source_broadcaster"]) is None else TwitchUser.deserialize(sb)
        v.type = x["type"]
        v._http = _get_http()
        return v
        
    attrs = _TwitchMessageTypeAttrs
    attrs.entry("broadcaster").readonly(utils.SimpleGetAttribute())
    attrs.entry("author").readonly(utils.SimpleGetAttribute("chatter"))
    attrs.entry("id").readonly(lambda o,n: script.wrap_python_value(UUID(o.inner.id)))
    attrs.entry("text").readonly(utils.SimpleGetAttribute())
    attrs.entry("reply").readonly(utils.SimpleGetAttribute())
    attrs.entry("type").readonly(utils.SimpleGetAttribute())
    attrs.entry(*_COLOR_NAMES).readonly(utils.SimpleGetAttribute())

_TwitchContextTypeAttrs = utils.ScriptAttributeHandler[BotScriptContext,Any](no_subscripting=True)
@_TwitchContextTypeAttrs.enforce_child_attrs()
@_TwitchContextTypeAttrs.attach
class _TwitchContextType(script.ScriptDataType[BotScriptContext]):
    attrs = _TwitchContextTypeAttrs
    attrs.entry("command").readonly(utils.SimpleGetAttribute("command_ctx"))
    attrs.entry("redeem").readonly(utils.SimpleGetAttribute())
    attrs.entry("message").readonly(utils.SimpleGetAttribute())
    attrs.entry("cheer").readonly(utils.SimpleGetAttribute())
    attrs.entry("bitsuse").readonly(utils.SimpleGetAttribute())
    attrs.entry("follow").readonly(utils.SimpleGetAttribute())
    attrs.entry("hype_train_begin").readonly(utils.SimpleGetAttribute("train_begin"))
    attrs.entry("hype_train_progress").readonly(utils.SimpleGetAttribute("train_progress"))
    attrs.entry("hype_train_end").readonly(utils.SimpleGetAttribute("train_end"))
    attrs.entry("raid").readonly(utils.SimpleGetAttribute())
    attrs.entry("sub").readonly(utils.SimpleGetAttribute())
    attrs.entry("gift_sub").readonly(utils.SimpleGetAttribute())
    attrs.entry("sub_msg").readonly(utils.SimpleGetAttribute())
        

TwitchUser = _TwitchUserType("TwitchUser", twitchio.PartialUser, script.BASE_TYPE)
TwitchFullUser = _TwitchFullUserType("TwitchFullUser", twitchio.User, TwitchUser)
TwitchChatter = _TwitchChatterType("TwitchChatter", twitchio.Chatter, TwitchUser)
TwitchAsset = _TwitchAssetType("TwitchAsset", twitchio.Asset, script.BASE_TYPE)
TwitchMessageBadge = _TwitchMessageBadgeType("TwitchMessageBadge", twitchio.ChatMessageBadge, script.BASE_TYPE)
TwitchMessageCheer = _TwitchMessageCheerType("TwitchMessageCheer", twitchio.ChatMessageCheer, script.BASE_TYPE)
TwitchMessageReply = _TwitchMessageReplyType("TwitchMessageReply", twitchio.ChatMessageReply, script.BASE_TYPE)
TwitchMessageFragment = _TwitchMessageFragmentType("TwitchMessageFragment", twitchio.ChatMessageFragment, script.BASE_TYPE)
TwitchMessageCheermote = _TwitchMessageCheermoteType("TwitchMessageCheermote", twitchio.ChatMessageCheermote, script.BASE_TYPE)
TwitchMessageEmote = _TwitchMessageEmoteType("TwitchMessageEmote", twitchio.ChatMessageEmote, script.BASE_TYPE)
TwitchMessage = _TwitchMessageType("TwitchMessage", twitchio.ChatMessage, script.BASE_TYPE)
TwitchCommandContext = _TwitchCommandContextType("TwitchCommandContext", commands.Context, script.BASE_TYPE)
TwitchRedeem = _TwitchRedeemType("TwitchRedeem", twitchio.ChannelPointsRedemptionAdd, script.BASE_TYPE)
TwitchReward = _TwitchRewardType("TwitchReward", twitchio.ChannelPointsReward, script.BASE_TYPE)
TwitchRewardLimitSettings = builtins.pair_alias_subtype("TwitchRewardLimitSettings", ["enabled"], ["value"], twitchio.RewardLimitSettings)
TwitchContext = _TwitchContextType("TwitchContext", BotScriptContext, script.BASE_TYPE)

AnalyticsWindow = _AnalyticsWindowType("AnalyticsWindow", analytics_window, builtins.Pair)

def get_tctx(ctx:script.ScriptContext):
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

f_send_twitch_message = ScriptFunction()
f_twitch_shoutout = ScriptFunction()
f_twitch_timeout = ScriptFunction()
f_twitch_ban = ScriptFunction()
f_twitch_unban = ScriptFunction()
f_current_twitch_stream_window = ScriptFunction()
f_is_this_twitch_user_first_message = ScriptFunction()
f_is_this_twitch_channel_first_message = ScriptFunction()
f_is_this_twitch_user_first_redeem = ScriptFunction()
f_is_this_twitch_channel_first_redeem = ScriptFunction()
f_count_redemptions_for_twitch_user = ScriptFunction()
f_count_redemptions_for_twitch_channel = ScriptFunction()

@f_send_twitch_message.overload(("msg", builtins.String), pass_ctx=True)
async def send_twitch_message_autodest(ctx:script.ScriptContext, msg:ScriptVariable[str]):
    tctx = get_tctx(ctx)
    await _resolve_broadcaster(tctx).send_message(msg.get().inner, tctx.bot.user)

@f_send_twitch_message.overload(("msg", builtins.String), ("broadcaster", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def send_twitch_message_manualdest(ctx:script.ScriptContext, msg:ScriptVariable[str], broadcaster:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = get_tctx(ctx)
    if broadcaster.get().inner is None:
        b = _resolve_broadcaster(tctx)
    else:
        b = await _resolve_user(tctx, broadcaster)
        if b is None:
            ... #TODO error could not resolve broadcaster
    await b.send_message(msg.get().inner, sender=tctx.bot.user)

@f_twitch_shoutout.overload(("user", _UserUnion), pass_ctx=True)
async def twitch_shoutout_autodest(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser]):
    tctx = get_tctx(ctx)
    await _resolve_broadcaster(tctx).send_shoutout(to_broadcaster=user.get().inner, moderator=tctx.bot.user)

@f_twitch_shoutout.overload(("user", _UserUnion), ("broadcaster", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def twitch_shoutout_manualdest(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser], broadcaster:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = get_tctx(ctx)
    if broadcaster.get().inner is None:
        b = _resolve_broadcaster(tctx)
    else:
        b = await _resolve_user(tctx, broadcaster)
        if b is None:
            ... #TODO error could not resolve broadcaster
    await b.send_shoutout(to_broadcaster=user, moderator=tctx.bot.user)

@f_twitch_timeout.overload(("user", _UserUnion), ("duration", [builtins.Integer, builtins.Float], 600), ("reason", [builtins.String, builtins.NullType], None), ("broadcaster", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def twitch_timeout(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser], duration:ScriptVariable[int|float], reason:ScriptVariable[str|None], broadcaster:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = get_tctx(ctx)
    if broadcaster.get().inner is None:
        b = _resolve_broadcaster(tctx)
    else:
        b = await _resolve_user(tctx, broadcaster)
        if b is None:
            ... #TODO error could not resolve broadcaster
    
    await b.timeout_user(user=user.get().inner, duration=duration.get().inner, reason=reason.get().inner, moderator=tctx.bot.user)

@f_twitch_ban.overload(("user", _UserUnion), ("reason", [builtins.String, builtins.NullType], None), ("broadcaster", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def twitch_ban(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser], reason:ScriptVariable[str|None], broadcaster:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = get_tctx(ctx)
    if broadcaster.get().inner is None:
        b = _resolve_user(tctx)
    else:
        b = await _resolve_user(tctx, broadcaster)
        if b is None:
            ... #TODO error could not resolve dest
    
    await b.ban_user(user=user.get().inner, reason=reason.get().inner, moderator=tctx.bot.user)

@f_twitch_unban.overload(("user", _UserUnion), pass_ctx=True)
async def twitch_unban_autodest(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser]):
    tctx = get_tctx(ctx)
    await _resolve_broadcaster(tctx).unban_user(user_id=user.get().inner, moderator=tctx.bot.user)

@f_twitch_unban.overload(("user", _UserUnion), ("broadcaster", _UserUnion), pass_ctx=True)
async def twitch_unban_manualdest(ctx:script.ScriptContext, user:ScriptVariable[str|int|twitchio.PartialUser], broadcaster:ScriptVariable[str|int|twitchio.PartialUser]):
    tctx = get_tctx(ctx)
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
    return script.wrap_python_value(analytics_window(None if executed.result is None else (r0 := executed.result[0] if isinstance(r0, datetime) else datetime.fromtimestamp(r0, timezone.utc))-timedelta(seconds=error), None))

async def _is_first_item(window:ScriptVariable[analytics_window], check_name:str, check_stat:type[analytics.Statistic], check, filter_parts:list[str], filter_values:list):
    aw = window.get().inner
    if not aw.is_empty:
        if not aw.is_start_open:
            filter_parts.append(f"{check_stat.COLUMN_HAPPENED} >= ?")
            filter_values.append(aw.first)
        if not aw.is_end_open:
            filter_parts.append(f"{check_stat.COLUMN_HAPPENED} <= ?")
            filter_values.append(aw.second)

    executed = await analytics.execute_statement_async(f"SELECT {check_name} FROM {check_stat.TABLE_NAME} WHERE {(" AND ".join(filter_parts))} ORDER BY {check_stat.COLUMN_HAPPENED} ASC", *filter_values, query_count=1)
    if executed.result is None or executed.result[0] != check:
        return builtins.false
    else:
        return builtins.true
    
async def _count_item(window:ScriptVariable[analytics_window], check_name:str, check_stat:type[analytics.Statistic], filter_parts:list[str], filter_values:list):
    aw = window.get().inner
    if not aw.is_empty:
        if not aw.is_start_open:
            filter_parts.append(f"{check_stat.COLUMN_HAPPENED} >= ?")
            filter_values.append(aw.first)
        if not aw.is_end_open:
            filter_parts.append(f"{check_stat.COLUMN_HAPPENED} <= ?")
            filter_values.append(aw.second)

    executed = await analytics.execute_statement_async(f"SELECT COUNT({check_name}) FROM {check_stat.TABLE_NAME} WHERE {(" AND ".join(filter_parts))}", *filter_values, query_count=1)
    if executed.result is None:
        return script.ScriptValue(builtins.Integer, 0)
    else:
        return script.ScriptValue(builtins.Integer, int(executed.result[0]))

@f_current_twitch_stream_window.overload(("broadcaster", _UserUnion+[builtins.NullType], None), ("threshold_secs", [builtins.Integer,builtins.Float], 0), ("threshold_mins", [builtins.Integer,builtins.Float], 0), ("threshold_hours", [builtins.Integer,builtins.Float], 0), ("error", [builtins.Integer,builtins.Float], 2.5), pass_ctx=True)
async def current_twitch_stream_window(ctx:script.ScriptContext, broadcaster:ScriptVariable[str|int|twitchio.PartialUser|None], threshold_secs:ScriptVariable[int|float], threshold_mins:ScriptVariable[int|float], threshold_hours:ScriptVariable[int|float], error:ScriptVariable[int|float]):
    tctx = get_tctx(ctx)
    seconds = threshold_secs.get().inner + threshold_mins.get().inner * 60 + threshold_hours.get().inner * 3600
    if broadcaster.get().inner is None:
        b = _resolve_broadcaster(tctx)
    else:
        b = await _resolve_user(tctx, broadcaster)
        if b is None:
            ... #TODO error could not resolve broadcaster
    return await _query_current_stream_window(int(b.id), seconds, error.get().inner)

@f_is_this_twitch_user_first_message.overload(("window", AnalyticsWindow), ("message", [builtins.UUID,TwitchMessage,builtins.NullType], None), ("author", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def is_this_twitch_user_first_message(ctx:script.ScriptContext, window:ScriptVariable[analytics_window], message:ScriptVariable[UUID|twitchio.ChatMessage|None], author:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = get_tctx(ctx)
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
            uid = int(msg.inner.chatter.id)
        msg = UUID(msg.inner.id)

    if uid is None:
        u = await _resolve_user(tctx, author)
        if u is None:
            ... #TODO error could not resolve provided author
        uid = int(u.id)
    
    return await _is_first_item(window, analytics.MessageStat.COLUMN_MESSAGE_ID, analytics.MessageStat, msg, [f"{analytics.MessageStat.COLUMN_AUTHOR_ID}=?"], [uid])
    

@f_is_this_twitch_channel_first_message.overload(("window", AnalyticsWindow), ("message", [builtins.UUID,TwitchMessage,builtins.NullType], None), pass_ctx=True)
async def is_this_twitch_channel_first_message(ctx:script.ScriptContext, window:ScriptVariable[analytics_window], message:ScriptVariable[UUID|twitchio.ChatMessage|None]):
    tctx = get_tctx(ctx)
    msg = message.get()

    if msg.inner is None:
        msg = UUID(_resolve_message(tctx).id)
    elif msg.type.issubtype(builtins.UUID):
        msg = msg.inner
    else:
        msg = UUID(msg.id)
    
    return await _is_first_item(window, analytics.MessageStat.COLUMN_MESSAGE_ID, analytics.MessageStat, msg, [], [])

@f_is_this_twitch_user_first_redeem.overload(("window", AnalyticsWindow), ("redeem", [builtins.UUID,TwitchRedeem,TwitchReward,builtins.NullType], None), ("user", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def is_this_twitch_user_first_redeem(ctx:script.ScriptContext, window:ScriptVariable[analytics_window], redeem:ScriptVariable[UUID|twitchio.ChannelPointsRedemptionAdd|twitchio.ChannelPointsReward|None], user:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = get_tctx(ctx)
    rdm = redeem.get()
    rwd = None
    usr = user.get()
    uid:int|None = None

    if rdm.inner is None:
        r = _resolve_redeem(tctx)
        if usr.inner is None:
            uid = int(r.user.id)
        rdm = UUID(r.id)
    elif rdm.type.issubtype(builtins.UUID):
        if usr.inner is None:
            ... #TODO error could not resolve redeem user
        rdm = rdm.inner
    elif rdm.type.issubtype(TwitchReward):
        if usr.inner is None:
            ... #TODO error could not resolve redeem user
        rwd = UUID(rdm.inner.id)
    else:
        if usr.inner is None:
            uid = int(rdm.inner.user.id)
        rdm = UUID(rdm.inner.id)

    if uid is None:
        u = await _resolve_user(tctx, user)
        if u is None:
            ... #TODO error could not resolve provided user
        uid = int(u.id)

    rdms = analytics.RedeemStat
    if rwd is None:
        return await _is_first_item(window, rdms.COLUMN_REDEEM_ID, rdms, rdm, [f"{rdms.COLUMN_AUTHOR_ID}=?"], [uid])
    else:
        return await _is_first_item(window, rdms.COLUMN_REWARD_ID, rdms, rwd, [f"{rdms.COLUMN_AUTHOR_ID}=?"], [uid])

@f_is_this_twitch_channel_first_redeem.overload(("window", AnalyticsWindow), ("redeem", [builtins.UUID,TwitchRedeem,TwitchReward,builtins.NullType], None), pass_ctx=True)
async def is_this_twitch_channel_first_redeem(ctx:script.ScriptContext, window:ScriptVariable[analytics_window], redeem:ScriptVariable[UUID|twitchio.ChannelPointsRedemptionAdd|twitchio.ChannelPointsReward|None]):
    tctx = get_tctx(ctx)
    rdm = redeem.get()
    rwd = None

    if rdm.inner is None:
        r = _resolve_redeem(tctx)
        rdm = UUID(r.id)
    elif rdm.type.issubtype(builtins.UUID):
        rdm = rdm.inner
    elif rdm.type.issubtype(TwitchReward):
        rwd = UUID(rdm.inner.id)
    else:
        rdm = UUID(rdm.inner.id)

    rdms = analytics.RedeemStat
    if rwd is None:
        return await _is_first_item(window, rdms.COLUMN_REDEEM_ID, rdms, rdm, [], [])
    else:
        return await _is_first_item(window, rdms.COLUMN_REWARD_ID, rdms, rwd, [], [])
    
@f_count_redemptions_for_twitch_user.overload(("window", AnalyticsWindow), ("reward", [builtins.UUID,TwitchRedeem,TwitchReward,builtins.NullType], None), ("user", _UserUnion+[builtins.NullType], None), pass_ctx=True)
async def count_redemptions_for_twitch_user(ctx:script.ScriptContext, window:ScriptVariable[analytics_window], reward:ScriptVariable[UUID|twitchio.ChannelPointsRedemptionAdd|twitchio.ChannelPointsReward|None], user:ScriptVariable[str|int|twitchio.PartialUser|None]):
    tctx = get_tctx(ctx)
    rwd = reward.get()
    usr = user.get()
    uid:int|None = None

    if rwd.inner is None:
        r = _resolve_redeem(tctx)
        if usr.inner is None:
            uid = int(r.user.id)
        rwd = UUID(r.reward.id)
    elif rwd.type.issubtype(builtins.UUID):
        if usr.inner is None:
            ... #TODO error could not resolve redeem user
        rwd = rwd.inner
    elif rwd.type.issubtype(TwitchReward):
        if usr.inner is None:
            ... #TODO error could not resolve redeem user
        rwd = UUID(rwd.inner.id)
    else:
        if usr.inner is None:
            uid = int(rwd.inner.user.id)
        rwd = UUID(rwd.inner.reward.id)

    if uid is None:
        u = await _resolve_user(tctx, user)
        if u is None:
            ... #TODO error could not resolve provided user
        uid = int(u.id)
    
    rdms = analytics.RedeemStat
    return await _count_item(window, rdms.COLUMN_REWARD_ID, rdms, [f"{rdms.COLUMN_AUTHOR_ID}=?"], [uid])

@f_count_redemptions_for_twitch_channel.overload(("window", AnalyticsWindow), ("reward", [builtins.UUID,TwitchRedeem,TwitchReward,builtins.NullType], None), pass_ctx=True)
async def count_redemptions_for_twitch_channel(ctx:script.ScriptContext, window:ScriptVariable[analytics_window], reward:ScriptVariable[UUID|twitchio.ChannelPointsRedemptionAdd|twitchio.ChannelPointsReward|None]):
    tctx = get_tctx(ctx)
    rwd = reward.get()

    if rwd.inner is None:
        r = _resolve_redeem(tctx)
        rwd = UUID(r.reward.id)
    elif rwd.type.issubtype(builtins.UUID):
        rwd = rwd.inner
    elif rwd.type.issubtype(TwitchReward):
        rwd = UUID(rwd.inner.id)
    else:
        rwd = UUID(rwd.inner.reward.id)
    
    rdms = analytics.RedeemStat
    return await _count_item(window, rdms.COLUMN_REWARD_ID, rdms, [], [])
    

def activate():
    utils.add_type(TwitchUser, constructor=False)
    utils.add_type(TwitchFullUser, constructor=False)
    utils.add_type(TwitchChatter, constructor=False)
    utils.add_type(TwitchAsset, constructor=False)
    utils.add_type(TwitchMessageBadge, constructor=False)
    utils.add_type(TwitchMessageCheer, constructor=False)
    utils.add_type(TwitchMessageReply, constructor=False)
    utils.add_type(TwitchMessageFragment, constructor=False)
    utils.add_type(TwitchMessageCheermote, constructor=False)
    utils.add_type(TwitchMessageEmote, constructor=False)
    utils.add_type(TwitchMessage, constructor=False)
    utils.add_type(TwitchCommandContext, constructor=False)
    utils.add_type(TwitchRedeem, constructor=False)
    utils.add_type(TwitchReward, constructor=False)
    utils.add_type(TwitchRewardLimitSettings, constructor=False)
    utils.add_type(TwitchContext, constructor=False)
    utils.add_type(AnalyticsWindow)
    script.SCRIPT_FUNCTION_TABLE["send_twitch_message"] = f_send_twitch_message
    script.SCRIPT_FUNCTION_TABLE["twitch_shoutout"] = f_twitch_shoutout
    script.SCRIPT_FUNCTION_TABLE["twitch_timeout"] = f_twitch_timeout
    script.SCRIPT_FUNCTION_TABLE["twitch_ban"] = f_twitch_ban
    script.SCRIPT_FUNCTION_TABLE["twitch_unban"] = f_twitch_unban
    script.SCRIPT_FUNCTION_TABLE["current_twitch_stream_window"] = f_current_twitch_stream_window
    script.SCRIPT_FUNCTION_TABLE["is_this_twitch_user_first_message"] = f_is_this_twitch_user_first_message
    script.SCRIPT_FUNCTION_TABLE["is_this_twitch_channel_first_message"] = f_is_this_twitch_channel_first_message
    script.SCRIPT_FUNCTION_TABLE["is_this_twitch_user_first_redeem"] = f_is_this_twitch_user_first_redeem
    script.SCRIPT_FUNCTION_TABLE["is_this_twitch_channel_first_redeem"] = f_is_this_twitch_channel_first_redeem
    script.SCRIPT_FUNCTION_TABLE["count_redemptions_for_twitch_user"] = f_count_redemptions_for_twitch_user
    script.SCRIPT_FUNCTION_TABLE["count_redemptions_for_twitch_channel"] = f_count_redemptions_for_twitch_channel

def deactivate():
    utils.remove_type(TwitchUser)
    utils.remove_type(TwitchFullUser)
    utils.remove_type(TwitchChatter)
    utils.remove_type(TwitchAsset)
    utils.remove_type(TwitchMessageBadge)
    utils.remove_type(TwitchMessageCheer)
    utils.remove_type(TwitchMessageReply)
    utils.remove_type(TwitchMessageFragment)
    utils.remove_type(TwitchMessageCheermote)
    utils.remove_type(TwitchMessageEmote)
    utils.remove_type(TwitchMessage)
    utils.remove_type(TwitchCommandContext)
    utils.remove_type(TwitchRedeem)
    utils.remove_type(TwitchReward)
    utils.remove_type(TwitchRewardLimitSettings)
    utils.remove_type(TwitchContext)
    utils.remove_type(AnalyticsWindow)
    utils.remove_function("send_twitch_message", f_send_twitch_message)
    utils.remove_function("twitch_shoutout", f_twitch_shoutout)
    utils.remove_function("twitch_timeout", f_twitch_timeout)
    utils.remove_function("twitch_ban", f_twitch_ban)
    utils.remove_function("twitch_unban", f_twitch_unban)
    utils.remove_function("current_twitch_stream_window", f_current_twitch_stream_window)
    utils.remove_function("is_this_twitch_user_first_message", f_is_this_twitch_user_first_message)
    utils.remove_function("is_this_twitch_channel_first_message", f_is_this_twitch_channel_first_message)
    utils.remove_function("is_this_twitch_user_first_redeem", f_is_this_twitch_user_first_redeem)
    utils.remove_function("is_this_twitch_channel_first_redeem", f_is_this_twitch_channel_first_redeem)
    utils.remove_function("count_redemptions_for_twitch_user", f_count_redemptions_for_twitch_user)
    utils.remove_function("count_redemptions_for_twitch_channel", f_count_redemptions_for_twitch_channel)