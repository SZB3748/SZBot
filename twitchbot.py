import actions
import aiohttp
import argparse
import asyncio
import atexit
import base64
import config
from datetime import datetime, timedelta
import exiting
import inspect
import json
import os
import pickle
import plugins
import runtime as rt
from simple_websocket.errors import ConnectionClosed
import threading
import traceback
import tronix
import twitch.analytics
import twitch.command_triggers
import twitch.redeem_triggers
import twitch.tronix_integrations as tti
import twitchio
from twitchio.ext import commands
from typing import Awaitable, Callable, Self
import uuid
import web
import websocket

API_BASE = ""
API_ENDPOINT = ""
API_WS_ENDPOINT = f""
TOKEN_REFRESH_ENDPOINT = "https://id.twitch.tv/oauth2/token"

def define_endpoints(host:str, port:int):
    global API_BASE, API_ENDPOINT, API_WS_ENDPOINT
    is_80 = port == 80
    is_443 = port == 443
    if is_80 or is_443:
        API_BASE = f"{host}/api"
    else:
        API_BASE = f"{host}:{port}/api"
    s = "s" * is_443
    API_ENDPOINT = f"http{s}://{API_BASE}"
    API_WS_ENDPOINT = f"ws{s}://{API_BASE}"

parser = argparse.ArgumentParser(description="SZBot twitchbot program.")
parser.add_argument("-d", "--addr", default=f"{web.HOST}:{web.PORT}", help="The address main.py is listening on.")
parser.add_argument("-p", "--plugin-configs", default=config.PLUGIN_FILE, help="Path to the plugin config file to use.")
parser.add_argument("-c", "--configs", default=config.CONFIG_FILE, help="Path to the config file to use.")
parser.add_argument("-C", "--bot-component", action="append", default=[], help="Set modes for twitchbot components (twitchbot:*) with <name>=<mode> syntax. These modes can be normal|remote|off")

def get_args()->tuple[tuple[str, int], str, str, dict[str, str|None]]:
    args = parser.parse_args()
    addr_arg:str = args.addr
    if ":" in addr_arg:
        host, port = addr_arg.split(":", 1)
        host = host.strip().lower()
        # using localhost can cause significant slowdowns for the
        # API proxy on Windows. cite: https://stackoverflow.com/a/75425128
        if host == "localhost":
            host = "127.0.0.1"
        if host and port:
            if port.isdecimal():
                addr_arg = host, int(port)
            else:
                print("Address port must be an integer")
                exit(-1)
        elif port and not port.isdecimal():
            print("Address port must be an integer")
            exit(-1)
        else:
            addr_arg = host or web.HOST, int(port) if port else web.PORT
    elif addr_arg.isdecimal():
        addr_arg = web.HOST, int(addr_arg)
    else:
        host = addr_arg.strip().lower()
        addr_arg = "127.0.0.1" if host == "localhost" else host, web.PORT

    expressions:list[str] = args.bot_component
    components = {}
    for expr in expressions:
        if "=" in expr:
            name, modename = expr.split("=", 1)
            name = name.strip()
            modename = modename.strip().lower()
            if modename == "off":
                modename = None
            components[name] = modename
        else:
            print("Bot component must be in the <name>=<mode> format, got:", expr)
            exit(-1)
    
    return addr_arg, args.configs, args.plugin_configs, components


def ratelimit(max_times:int, duration:timedelta, limited_callback:Callable[[commands.Context, datetime], Awaitable[None]]|None=None, channel_list:set[str]|None=None, is_whitelist:bool=True):
    channels:dict[twitchio.PartialUser, dict[twitchio.PartialUser|twitchio.Chatter, list[datetime]]] = {}
    def decor(f:Callable[..., Awaitable]):
        async def wrapper(ctx:commands.Context, *args, **kwargs):
            if channel_list is None or bool(ctx.channel.id in channel_list) == bool(is_whitelist):
                if ctx.channel in channels:
                    users = channels[ctx.channel]
                else:
                    users = channels[ctx.channel] = {}
            
                if not ctx.author.moderator:
                    ctx.author.admin
                    now = datetime.now()
                    if ctx.author in users:
                        times = users[ctx.author]
                        i = 0
                        for t in times:
                            if now - t >= duration:
                                i += 1
                        if i > 0:
                            times = users[ctx.author] = times[i:]
                    else:
                        times = users[ctx.author] = []

                    if len(times) >= max_times:
                        if limited_callback:
                            await limited_callback(ctx, times[0])
                        return
                    else:
                        times.append(now)
                
            await f(ctx, *args, **kwargs)
        
        wrapper.__name__ = f.__name__
        wrapper.__doc__ = f.__doc__
        wrapper.__wrapped__ = f
        return wrapper
    
    return decor

type_names = {
    "str": "text",
    "int": "integer",
    "float": "number",
    "bool": "true|false"
}

value_names = {
    True: "true",
    False: "false"
}

OAUTH_SCOPES:set[str] = {
    "user:write:chat",
}

OAUTH_CHANNEL_SCOPES:set[str] = {
    "user:read:chat",
    "user:bot",
    "channel:bot",
    "channel:manage:redemptions",
    "bits:read",
    "moderator:read:followers",
    "channel:read:hype_train",
    "channel:read:subscriptions",
}

def _link_command_newfunc(name:str):
    async def func(ctx:commands.Context):
        configs = config.read()
        if "Links" not in configs:
            return
        links = configs["Links"]
        if isinstance(links, dict) and name in links:
            link = links[name]
            if isinstance(link, str):
                await ctx.send(link)
    func.__name__ = f"func_{name}"
    func.__doc__ = "Sends the associated text in chat."
    return func

class Bot(commands.AutoBot):
    def __init__(self, client_id, client_secret, bot_id, prefix:str|Callable[[Self, twitchio.ChatMessage], str],
                 subs:list[twitchio.eventsub.SubscriptionPayload], use_core_commands:bool=True):
        super().__init__(
            client_id=client_id,
            client_secret=client_secret,
            bot_id=bot_id,
            prefix=prefix,
            subscriptions=subs,
        )
        self.links_commands:set[str] = set()
        self._callback_command_triggers:dict[str, twitch.command_triggers.CallbackCommandTrigger] = {}
        self.command_triggers:dict[str, twitch.command_triggers.CommandTrigger] = {}
        self.subs = subs
        self.use_core_commands = use_core_commands
        self._loop = None

    def add_command(self, command:twitch.command_triggers.CommandTrigger|commands.Command):
        if isinstance(command, twitch.command_triggers.CommandTrigger):
            self.command_triggers[command.name] = command
            if isinstance(command, twitch.command_triggers.CallbackCommandTrigger):
                self._callback_command_triggers[command.name] = command
            command = command.to_twitch_command()
        return super().add_command(command)
    
    def remove_command(self, name:str|twitch.command_triggers.CommandTrigger):
        if isinstance(name, twitch.command_triggers.CommandTrigger):
            name = name.name
        command = self.command_triggers.pop(name, None)
        if isinstance(command, twitch.command_triggers.CallbackCommandTrigger) and name in self._callback_command_triggers:
            del self._callback_command_triggers[name]
        return super().remove_command(name)

    def sync_commands(self):
        loaded_commands = twitch.command_triggers.load_command_triggers()
        cmd_difference = set(self.command_triggers.keys()) ^ set(loaded_commands.keys())
        for name in cmd_difference:
            if name in loaded_commands:
                self.add_command(loaded_commands[name])
            else: #name in self.command_triggers
                cmd = self.command_triggers[name]
                if isinstance(cmd, twitch.command_triggers.CallbackCommandTrigger):
                    continue #command would be reassigned pointlessly so just do nothing
                ccmd = self._callback_command_triggers.get(name,None)
                if ccmd is None:
                    del self.command_triggers[name]
                else:
                    self.command_triggers[name] = ccmd
        for name, lcmd in loaded_commands.items():
            if name in cmd_difference:
                continue #was added already
            cmd = self.command_triggers[name]
            assert isinstance(cmd, twitch.command_triggers.ActionCommandTrigger)
            cmd.update(lcmd)

    def update_link_commands(self):
        configs = config.read()
        if "Links" in configs:
            links:dict[str] = configs["Links"]
            if isinstance(links, dict):
                sym_difference = self.links_commands ^ set(links.keys()) #values that aren't in both sets
                for name in sym_difference:
                    if name in links:
                        cb = _link_command_newfunc(name)
                        ct = twitch.command_triggers.CallbackCommandTrigger.new(cb, name)
                        self.add_command(ct)
                        self.links_commands.add(name)
                    else: #name in self.links_commands
                        self.remove_command(name)
                        self.links_commands.remove(name)
                return
        for name in self.links_commands:
            self.remove_command(name)
    
    def get_matches(self, event, merged:dict[str, twitch.event_triggers.EventTrigger], matchers:dict[str, Callable]):
        matched = []
        for trigger in merged.values():
            if trigger.match(event, matchers):
                matched.append(trigger)
        return matched
    
    async def run_matches(self, event, matched:list[twitch.event_triggers.EventTrigger]):
        for trigger in matched:
            c = trigger.handle(self, event)
            if inspect.isawaitable(c):
                await c


    async def setup_hook(self):
        self.add_listener(self.event_follow)
        self.add_listener(self.event_cheer)
        self.add_listener(self.event_raid)
        self.add_listener(self.event_message)
        self.add_listener(self.event_bits_use)
        self.add_listener(self.event_custom_redemption_add)
        self.add_listener(self.event_hype_train)
        self.add_listener(self.event_hype_train_progress)
        self.add_listener(self.event_hype_train_end)
        self.add_listener(self.event_stream_online)
        self.add_listener(self.event_stream_offline)
        self.add_listener(self.event_subscription)
        self.add_listener(self.event_subscription_gift)
        self.add_listener(self.event_subscription_message)
        if self.use_core_commands:
            await self.add_component(CoreComponent(self))

    async def add_token(self, token:str, refresh:str)->twitchio.authentication.ValidateTokenPayload:
        resp:twitchio.authentication.ValidateTokenPayload = await super().add_token(token, refresh)

        respdata = {"token": token, "refresh_token": refresh}
        oauth = config.read(config.OAUTH_TWITCH_FILE)
        channels = oauth.get("channels", None)
        user = await self.fetch_user(id=resp.user_id)
        print("added token for user", user)
        if isinstance(channels, dict):
            channels[user.name] = respdata
        else:
            channels = {user.name: respdata}
        config.write(config_updates={"channels": channels}, path=config.OAUTH_TWITCH_FILE)

    async def event_ready(self):
        self._loop = asyncio.get_running_loop()
        await bot.delete_all_eventsub_subscriptions()
        oauth = config.read(path=config.OAUTH_TWITCH_FILE)
        channels = oauth.get("channels",None)
        if isinstance(channels, dict):
            for d in channels.values():
                if isinstance(d, dict):
                    await self.add_token(d["token"], d["refresh_token"])
        resp:twitchio.MultiSubscribePayload = await self.multi_subscribe(self.subs)
        if resp.errors:
            print("Failed to subscribe to", repr(resp.errors))
        else:
            print("Successfully subscribed")

        bot.sync_commands()

        print("twitch bot ready")

    async def event_follow(self, payload:twitchio.ChannelFollow):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> new follow: {payload.user}")
        await self.run_matches(payload, self.get_matches(payload, twitch.follow_triggers.merge_follow_triggers(), twitch.follow_triggers.CONDITION_MATCHERS))
    
    async def event_cheer(self, payload:twitchio.ChannelCheer):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> {payload.user} cheered {payload.bits}: {payload.message}")
        await self.run_matches(payload, self.get_matches(payload, twitch.bits_triggers.merge_cheer_triggers(), twitch.bits_triggers.CHEER_CONDITION_MATCHERS))

    async def event_raid(self, payload:twitchio.ChannelRaid):
        await self.run_matches(payload, self.get_matches(payload, twitch.raid_triggers.merge_raid_triggers(), twitch.raid_triggers.CONDITION_MATCHERS))

    async def event_message(self, message:twitchio.ChatMessage) -> None:      
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{message.broadcaster}> {message.chatter}: {message.text}")
        await twitch.analytics.insert_stat_async(twitch.analytics.MessageStat.from_data(message))
        if message.chatter.id == self.bot_id and not message.chatter.broadcaster:
            return
        
        self.update_link_commands()
        await self.run_matches(message, self.get_matches(message, twitch.message_triggers.merge_message_triggers(), twitch.message_triggers.CONDITION_MATCHERS))
        await self.process_commands(message)

    async def event_command_error(self, payload:commands.CommandErrorPayload):
        if isinstance(payload.exception, commands.ArgumentError):
            await payload.context.send("Bad command usage. Use !help <command_name> to view command usage details.")
            print("command error:", type(payload.exception).__name__, payload.exception)
        else:
            print("command error:")
            traceback.print_exception(payload.exception)

    async def event_bits_use(self, payload:twitchio.ChannelBitsUse):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> {payload.user} used {payload.bits} bits")
        await self.run_matches(payload, self.get_matches(payload, twitch.bits_triggers.merge_bitsuse_triggers(), twitch.bits_triggers.BITSUSE_CONDITION_MATCHERS))

    async def event_custom_redemption_add(self, payload:twitchio.ChannelPointsRedemptionAdd):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> {payload.user} redeemed {payload.reward.title} ({payload.reward.id}//{payload.id})")
        await twitch.analytics.insert_stat_async(twitch.analytics.RedeemStat.from_data(payload))
        await self.run_matches(payload, self.get_matches(payload, twitch.redeem_triggers.merge_redeem_triggers(), twitch.redeem_triggers.CONDITION_MATCHERS))
        
    async def event_hype_train(self, payload:twitchio.HypeTrainBegin):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> hype train started")
        await self.run_matches(payload, self.get_matches(payload, twitch.hypetrain_triggers.merge_hypetrain_begin_triggers(), twitch.hypetrain_triggers.BEGIN_CONDITION_MATCHERS))

    async def event_hype_train_progress(self, payload:twitchio.HypeTrainProgress):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> hype train progress")
        await self.run_matches(payload, self.get_matches(payload, twitch.hypetrain_triggers.merge_hypetrain_progress_triggers(), twitch.hypetrain_triggers.PROGRESS_CONDITION_MATCHERS))

    async def event_hype_train_end(self, payload:twitchio.HypeTrainEnd):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> hype train end")
        await self.run_matches(payload, self.get_matches(payload, twitch.hypetrain_triggers.merge_hypetrain_end_triggers(), twitch.hypetrain_triggers.END_CONDITION_MATCHERS))

    async def event_subscription(self, payload:twitchio.ChannelSubscribe):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> subscription: {payload.user}")
        await self.run_matches(payload, self.get_matches(payload, twitch.sub_triggers.merge_sub_triggers(), twitch.sub_triggers.SUB_CONDITION_MATCHERS))

    async def event_subscription_gift(self, payload:twitchio.ChannelSubscriptionGift):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> {payload.user} gifted a sub")
        await self.run_matches(payload, self.get_matches(payload, twitch.sub_triggers.merge_gift_sub_triggers(), twitch.sub_triggers.GSUB_CONDITION_MATCHERS))

    async def event_subscription_message(self, payload:twitchio.ChannelSubscriptionMessage):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> {payload.user} announced their sub: {payload.message}")
        await self.run_matches(payload, self.get_matches(payload, twitch.sub_triggers.merge_sub_msg_triggers(), twitch.sub_triggers.SUB_MSG_CONDITION_MATCHERS))

    async def event_stream_online(self, payload:twitchio.StreamOnline):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> went live")
        await twitch.analytics.insert_stat_async(twitch.analytics.StreamStartStat.from_data(payload))
    
    async def event_stream_offline(self, payload:twitchio.StreamOffline):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{payload.broadcaster}> is now offline")
        await twitch.analytics.insert_stat_async(twitch.analytics.StreamEndStat.from_data(payload))


class CoreComponent(commands.Component):
    def __init__(self, bot:Bot):
        self.bot = bot
        for attr in type(self).__dict__.values():
            if isinstance(attr, twitch.command_triggers.CallbackCommandTrigger):
                self.bot.add_command(twitch.command_triggers.CallbackCommandTrigger(
                    attr.name,
                    attr.description,
                    attr.signature,
                    attr.permissions,
                    attr.callback,
                    bind=self
                ))

    @twitch.command_triggers.CallbackCommandTrigger.create("help")
    async def help_command(self, ctx:commands.Context, command_name:str=None):
        """Lists and describes commands."""
        self.bot.sync_commands()
        command_data = twitch.command_triggers.load_commands()

        if command_name is None:
            #exclude commands that user does not meet requirements for
            names = []
            for name, ct in self.bot.command_triggers.items():
                if isinstance(ct, twitch.command_triggers.CallbackCommandTrigger):
                    cmd = ct.generate_command()
                elif name in command_data:
                    cmd = command_data[name]
                else:
                    ... #TODO command trigger has no corresponding data
                if cmd.permissions.meets_requirements(ctx.author):
                    names.append(name)
            await ctx.send("Commands: " + ", ".join(names))
        elif command_name not in self.bot.commands:
            await ctx.send(f"Command {command_name} does not exist.")
        else:
            ct = self.bot.command_triggers.get(command_name, None)
            if ct is None:
                await ctx.send(f"Command {command_name} has no help info.")
            else:
                if isinstance(ct, twitch.command_triggers.CallbackCommandTrigger):
                    cmd = ct.generate_command()
                elif command_name in command_data:
                    cmd = command_data[command_name]
                else:
                    ... #TODO command trigger has no corresponding data
                
                if not cmd.permissions.meets_requirements(ctx.author):
                    await ctx.send(f"You cannot use this command.")
                else:
                    signature = cmd.signature.generate_str("!", command_name)
                    r = []
                    if cmd.description:
                        r.append(cmd.description)
                    r.append(f"Usage: {signature}")
                    await ctx.send(" ".join(r))


    @twitch.command_triggers.CallbackCommandTrigger.create("links")
    async def links_command(self, ctx:commands.Context):
        """Lists names of all link commands."""
        if bot.links_commands:
            await ctx.send(", ".join(name for name in bot.links_commands))

    @twitch.command_triggers.CallbackCommandTrigger.create("pload", permissions=twitch.command_triggers.CommandPermissions(requires_moderator=True))
    async def plugin_load(self, ctx:commands.Context, name:str):
        """Loads a plugin with the give name."""
        if not ctx.author.moderator:
            return
        
        plugin = plugins.shared_plugins_list.get(name, None)
        if plugin is not None:
            if plugin.module is None:
                await ctx.send(f"Plugin {name} is disabled")
                return
            plugin.twitch_bot_load(plugins.TwitchBotLoadEvent(plugins.shared_plugins_list, plugin, pconfig_path, False, bot))
            r = await pload_request("load", name)
            if r.ok:
                await ctx.send(f"Loaded plugin {name}")
                return
            else:
                print(f"[fail] /api/plugins/load name={name} ({r.status})")
        await ctx.send(f"Failed to load plugin {name}")

    @twitch.command_triggers.CallbackCommandTrigger.create("punload", permissions=twitch.command_triggers.CommandPermissions(requires_moderator=True))
    async def plugin_unload(self, ctx:commands.Context, name:str):
        """Unloads a plugin with the given name."""
        if not ctx.author.moderator:
            return
        
        plugin = plugins.shared_plugins_list.get(name, None)
        if plugin is not None:
            if plugin.module is None:
                await ctx.send(f"Plugin {name} is disabled")
                return
            plugin.twitch_bot_unload(plugins.TwitchBotUnloadEvent(plugins.shared_plugins_list, plugin, False, None))
            r = await pload_request("unload", name)
            if r.ok:
                await ctx.send(f"Unloaded plugin {name}")
                return
            else:
                print(f"[fail] /api/plugins/unload name={name} ({r.status})")
        await ctx.send(f"Failed to unload plugin {name}")

async def pload_request(action:str, name:str):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_ENDPOINT}/plugins/{action}", data={"name": name}) as r:
            return r

def get_init_ids(client_id, client_secret, bot_name:str, channels:list[str])->tuple[str, list[twitchio.User]]:
    async def _func():
        async with twitchio.Client(client_id=client_id, client_secret=client_secret) as client:
            await client.login()
            botusr = await client.fetch_user(login=bot_name)
            if channels:
                channel_ids = await client.fetch_users(logins=channels)
            else:
                channel_ids = []
            return None if botusr is None else botusr.id, channel_ids
    _loop = asyncio.new_event_loop()
    rtv = _loop.run_until_complete(_func())
    _loop.close()
    return rtv

#set up the bot
def init_bot(old_bot:Bot|None=None):
    m = plugins.parse_plugin_meta(plugins.CORE_CONFIGS_META)
    c = plugins.config_apply_meta(config.read(), m.configs)
    oauth = config.read(path=config.OAUTH_TWITCH_FILE)
    identity = oauth.get("identity", None)

    if not (isinstance(identity, dict) and "Token" in identity and "Client-Id" in identity and "Client-Secret" in identity and "Prefix" in c):
        return None
    
    client_id = identity.get("Client-Id")
    client_secret = identity.get("Client-Secret")
    bot_name = identity.get("Bot-Name")
    channels = oauth.get("channels", None)

    bot_id, ids = get_init_ids(client_id, client_secret, bot_name, list(channels.keys()) if isinstance(channels, dict) else None)
    subs = []
    for user in ids:
        subs.extend([
            twitchio.eventsub.ChatMessageSubscription(broadcaster_user_id=user.id, user_id=bot_id),
            twitchio.eventsub.StreamOnlineSubscription(broadcaster_user_id=user.id),
            twitchio.eventsub.StreamOfflineSubscription(broadcaster_user_id=user.id),
            twitchio.eventsub.ChannelFollowSubscription(broadcaster_user_id=user.id, moderator_user_id=user.id),
            twitchio.eventsub.ChannelSubscribeSubscription(broadcaster_user_id=user.id),
            twitchio.eventsub.ChannelSubscriptionGiftSubscription(broadcaster_user_id=user.id),
            twitchio.eventsub.ChannelSubscribeMessageSubscription(broadcaster_user_id=user.id),
            twitchio.eventsub.ChannelRaidSubscription(to_broadcaster_user_id=user.id),
            twitchio.eventsub.ChannelRaidSubscription(from_broadcaster_user_id=user.id),
            twitchio.eventsub.ChannelPointsRedeemAddSubscription(broadcaster_user_id=user.id),
            twitchio.eventsub.ChannelCheerSubscription(broadcaster_user_id=user.id),
            twitchio.eventsub.ChannelBitsUseSubscription(broadcaster_user_id=user.id),
            twitchio.eventsub.HypeTrainBeginSubscription(broadcaster_user_id=user.id),
            twitchio.eventsub.HypeTrainProgressSubscription(broadcaster_user_id=user.id),
            twitchio.eventsub.HypeTrainEndSubscription(broadcaster_user_id=user.id),
        ])

    bot = Bot(client_id, client_secret, bot_id, c["Prefix"], subs)

    if old_bot is not None:
        old_bot.close()
        for cog in old_bot._components.values():
            bot.add_component(cog)
        for command in old_bot._commands.values():
            bot.add_command(command)
        bot.__modules.update(old_bot.__modules)
        bot._callback_command_triggers.update(old_bot._callback_command_triggers)
        bot.links_commands.update(old_bot.links_commands)
        bot.command_triggers.update(old_bot.command_triggers)
        bot.use_core_commands = old_bot.use_core_commands
    return bot


_arl_futures:dict[uuid.UUID, asyncio.Future] = {}
_arl_futures_lock = threading.Lock()



async def _action_runner_local_task(ws:websocket.WebSocket, task_id:uuid.UUID, scripts:list[tuple[uuid.UUID, tronix.Script]]):
    try:
        results = await actions.run_scripts(*scripts)
        script_lookup = {uid:script for uid, script, *_ in scripts}
        print(f"script env switch: finished running scripts: {", ".join(str(uid) for uid, *_ in results)}")
        ws.send(json.dumps({
            "instruction": "done",
            "scripts": {
                str(uid): {
                    "success": success,
                    "return_value": actions.serialize_script_return_value(script_lookup[uid])
                }
                for uid, success, *_ in results
            }
        }))
    finally:
        with _arl_futures_lock:
            _arl_futures.pop(task_id,None)

def ws_on_open(ws):
    print("connected to script env switch as", actions.current_environment_name)

def ws_on_reconnect(ws):
    print("reconnected to script env switch")

def ws_on_message(ws:websocket.WebSocket, msg:str|bytearray|memoryview):
    if isinstance(msg, memoryview):
        msg = msg.tobytes()
    data = json.loads(msg)
    if not isinstance(data, dict):
        return
    instruction = data["instruction"]
    print("script env switch got instruction:", instruction)
    if instruction == "run":
        assert bot._loop is not None, "Twitchbot _loop was not set"
        scripts = data.get("scripts",None)
        if isinstance(scripts, list):
            add_run = []
            for sdata in scripts:
                if not isinstance(sdata, dict):
                    continue
                env = sdata["env"]
                if env is None:
                    continue
                elif actions.match_environment_name(env, actions.current_environment_name):
                    script = sdata["script"]
                    if isinstance(script, dict):
                        uid = uuid.UUID(sdata["uid"])
                        scope_ser = pickle.loads(base64.b64decode(script["scope"]))
                        if isinstance(scope_ser, dict):
                            scope = tronix.utils.deserialize_namespace(scope_ser)
                            scope.setdefault(tti.TWITCH_CONTEXT_VAR_NAME, tronix.script.ScriptVariable(tronix.script.wrap_python_value(tti.BotScriptContext(bot))))
                        else:
                            scope = scope_ser
                        s = tronix.Script(script["content"], scope)
                        add_run.append((uid, s, env))
            if add_run:
                print(f"script env switch: running scripts: {", ".join(str(uid) for uid, *_ in add_run)}")
                task_id = uuid.uuid4()
                with _arl_futures_lock:
                    _arl_futures[task_id] = asyncio.run_coroutine_threadsafe(_action_runner_local_task(ws, task_id, add_run), loop=bot._loop)
    elif instruction == "done":
        #TODO refactor to handle return values
        scripts = data.get("scripts",None)
        if isinstance(scripts, dict):
            for id_s, values in scripts.items():
                if not isinstance(values, dict):
                    continue
                success = values.get("success", False)
                return_value = values.get("return_value", None)
                uid = uuid.UUID(id_s)
                de = actions._env_switch_done.get(uid,None)
                if de is not None:
                    de.mark_done(bool(success), actions.deserialize_script_return_value(return_value))
    elif instruction == "error":
        ...

def ws_on_error(ws, e:Exception):
    if isinstance(e, (ConnectionRefusedError, ConnectionClosed)):
        print(f"script env switch error ({type(e).__name__}):", e)
    else:
        print(f"script env switch error ({type(e).__name__}):")
        traceback.print_exception(e)

def ws_on_close(ws, status_code, msg:str|bytearray|memoryview):
    print("disconnected from script env switch")


def _twitchbot_enque_script(uid:uuid.UUID, environment:str, s:tronix.Script, is_done:actions._env_switch_done_entry):
    ws.send(json.dumps({
        "instruction": "run",
        "scripts": [
            {
                "uid": str(uid),
                "env": environment,
                "script": {
                    "content": s.raw,
                    "scope": web._scope_to_b64(s.scope)
                } if isinstance(s, tronix.Script) else s
            }
        ]
    }))
    with actions._env_switch_queue_lock:
        actions._env_switch_done[uid] = is_done
    return uid, environment, s, is_done

actions._enqueue_script = _twitchbot_enque_script

def ws_run():
    _cleanup = exiting.make_websocket_cleanup(ws,
        "closing script environment switch websocket",
        "closed script environment switch websocket"
    )
    ws.run_forever(reconnect=5)
    exiting.unregister_cleanup_listener(_cleanup)

async def main():
    await bot.start(load_tokens=False, save_tokens=False)

bot:Bot|None = None

def exit_handler(e:Exception=None):
    atexit.unregister(exit_handler)
    print("unloading enabled plugins")
    for plugin in rt.plugin_list.values():
        if plugin.module is not None:
            plugin.twitch_bot_unload(plugins.TwitchBotUnloadEvent(rt.plugin_list, plugin, True, e))
    print("unloaded plugins")

    if ws_thread is not None and ws_thread.is_alive():
        ws.close()
        ws_thread.join()

    if analytics_thread is not None and analytics_thread.is_alive():
        twitch.analytics.sqle_stop()
        analytics_thread.join()

if __name__ == "__main__":
    actions.current_environment_name = actions.generate_environment_name("twitchbot")

    addr, config_path, pconfig_path, components = get_args()
    config.CONFIG_FILE = config_path
    define_endpoints(*addr)

    #assign __main__ over twitchbot so importing twitchbot imports __main__ instead
    #and the redefinition of the endpoints is used by plugins instead of the defaults
    import os, sys
    this = sys.modules[__name__]
    modname = os.path.basename(__file__).rsplit(".", 1)[0]
    sys.modules[modname] = this

    bot = init_bot()
    if bot is None:
        print("You must run main.py first to make sure your oauth_twitch.json file is fine.\nAlso, make sure to make a config.json file with your bot's \"Prefix\".")
        exit(-1)

    ws = websocket.WebSocketApp(
        f"{API_WS_ENDPOINT}/action/script/env-switch?name={actions.current_environment_name}",
        on_open=ws_on_open, on_message=ws_on_message,
        on_error=ws_on_error, on_close=ws_on_close,
        on_reconnect=ws_on_reconnect
    )

    print("reading plugin list")
    rt.plugin_list = plugins.read_plugin_data(pconfig_path)
    plugin_enabled_count = sum(1 for plugin in rt.plugin_list.values() if plugin.module is not None)
    print("read", len(rt.plugin_list), "plugins with", plugin_enabled_count, "enabled plugins")
    print("generating plugin load order")
    load_order = plugins.generate_load_order(rt.plugin_list)
    print("loading enabled plugins")
    for plugin_name in load_order:
        plugin = rt.plugin_list[plugin_name]
        if plugin.module is not None and plugin.startup_load:
            plugin.twitch_bot_load(plugins.TwitchBotLoadEvent(plugin, pconfig_path, True, bot))
    print("loaded plugins")

    if components:
        commands_mode = components.get(plugins.TWITCHBOT_COMPONENT_COMMANDS, plugins.COMPONENT_MODE_NORMAL)
        tronix_mode = components.get(plugins.TWITCHBOT_COMPONENT_TRONIX, plugins.COMPONENT_MODE_NORMAL)
        analytics_mode = components.get(plugins.TWITCHBOT_COMPONENT_ANALYTICS, plugins.COMPONENT_MODE_NORMAL)
    else:
        commands_mode = tronix_mode = analytics_mode = plugins.COMPONENT_MODE_NORMAL
    
    bot.use_core_commands = commands_mode == plugins.COMPONENT_MODE_NORMAL

    assert tronix_mode != plugins.COMPONENT_MODE_REMOTE, "Twitchbot tronix has no remote mode."
    assert analytics_mode != plugins.COMPONENT_MODE_REMOTE, "Twitchbot analytics has no remote mode."
    if tronix_mode == plugins.COMPONENT_MODE_NORMAL:
        print("loading script environment")
        import tronix_integrations
        tronix_integrations.activate(plugins.COMPONENT_MODE_NORMAL)
        print("loaded script environment")

        print("starting script env switch connection")
        ws_thread = threading.Thread(target=ws_run)
        ws_thread.start()
    else:
        ws_thread = None

    if analytics_mode == plugins.COMPONENT_MODE_NORMAL:
        print("setting up analytics")
        analytics_thread = threading.Thread(target=twitch.analytics.sql_executor_loop_handle, daemon=True)
        analytics_thread.start()
    else:
        analytics_thread = None

    e = None
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("^C")
    except Exception as _e:
        traceback.print_exception(_e)
        e = _e

    exit_handler(e)
