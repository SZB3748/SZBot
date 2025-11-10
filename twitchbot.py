import aiohttp
import argparse
import asyncio
import config
from datetime import datetime, timedelta
import events
import inspect
import json
import plugins
import threading
import traceback
from typing import Awaitable, Callable, Self
import twitchio
from twitchio.ext import commands
import web
import websocket

twitchio.eventsub

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

def get_args()->tuple[tuple[str, int], str]:
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
    
    return addr_arg, args.configs, args.plugin_configs

class CommandAnnotation:
    def __init__(self, spec:inspect.Signature, doc:str,
                 requires_admin:bool=False, requires_artist:bool=False, requires_broadcaster:bool=False, requires_founder:bool=False,
                 requires_moderator:bool=False, requires_no_audio:bool=False, requires_no_video:bool=False, requires_prime:bool=False, requires_staff:bool=False,
                 requires_subscriber:bool=False, requires_turbo:bool=False, requires_verified:bool=False, requires_vip:bool=False):
        self.spec = spec
        self.doc = doc
        self.requires_admin = requires_admin
        self.requires_artist = requires_artist
        self.requires_broadcaster = requires_broadcaster
        self.requires_founder = requires_founder
        self.requires_moderator = requires_moderator
        self.requires_no_audio = requires_no_audio
        self.requires_no_video = requires_no_video
        self.requires_prime = requires_prime
        self.requires_staff = requires_staff
        self.requires_subscriber = requires_subscriber
        self.requires_turbo = requires_turbo
        self.requires_verified = requires_verified
        self.requires_vip = requires_vip

    def meets_requirements(self, author:twitchio.Chatter|twitchio.PartialUser):
        return not (
            self.requires_admin and not author.admin or self.requires_artist and not author.artist or
            self.requires_broadcaster and not author.broadcaster or self.requires_founder and not author.founder or
            self.requires_moderator and not author.moderator or self.requires_no_audio and not author.no_audio or
            self.requires_no_video and not author.no_video or self.requires_prime and not author.prime or
            self.requires_staff and not author.staff or self.requires_subscriber and not author.subscriber or
            self.requires_turbo and not author.turbo or self.requires_verified and not author._is_verified or
            self.requires_vip and not author.vip
        )

annotate_info:dict[str, CommandAnnotation] = {} #command_name: CommandAnnotation
_annotate_pre:dict[Callable, CommandAnnotation] = {} #func: CommandAnnotation

def annotate(requires_admin:bool=False, requires_artist:bool=False, requires_broadcaster:bool=False, requires_founder:bool=False,
                 requires_moderator:bool=False, requires_no_audio:bool=False, requires_no_video:bool=False, requires_prime:bool=False, requires_staff:bool=False,
                 requires_subscriber:bool=False, requires_turbo:bool=False, requires_verified:bool=False, requires_vip:bool=False, command_name:str|None=None, **kwargs):
    def decor(f:Callable):
        a = CommandAnnotation(inspect.signature(f), f.__doc__ or "", requires_admin, requires_artist, requires_broadcaster, requires_founder, requires_moderator, requires_no_audio, requires_no_video, requires_prime, requires_staff, requires_subscriber, requires_turbo, requires_verified, requires_vip, **kwargs)
        if command_name is None:
            _annotate_pre[f] = a
        else:
            annotate_info[command_name] = a
        return f
    return decor

def ratelimit(max_times:int, duration:timedelta, limited_callback:Callable[[commands.Context, datetime], Awaitable[None]]|None=None):
    users:dict[twitchio.PartialUser|twitchio.Chatter, list[datetime]] = {}

    def decor(f:Callable[..., Awaitable]):
        async def wrapper(ctx:commands.Context, *args, **kwargs):
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
                    await limited_callback(ctx, times[0])
                    return
                else:
                    times.append(now)
                
            await f(ctx, *args, **kwargs)
        
        wrapper.__name__ = f.__name__
        wrapper.__doc__ = f.__doc__
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
    "user:write:chat"
}

OAUTH_CHANNEL_SCOPES:set[str] = {
    "user:read:chat",
    "user:bot",
    "channel:bot",
    "channel:read:redemptions"
}

def get_command_signature(prefix:str, name:str, a:CommandAnnotation)->str:
    usage_hint = [prefix + name]
    if "ctx" in a.spec.parameters:
        param_items = list(a.spec.parameters.keys())
        start_index = param_items.index("ctx") + 1
    else:
        start_index = 0

    params = list(a.spec.parameters.values())
    for i in range(start_index, len(params)):
        param = params[i]
        if param.default is inspect.Parameter.empty:
            surround = "<>"
            default_hint = ""
        else:
            surround = "[]"
            default_hint = "" if param.default is None else f" = {value_names.get(param.default, param.default)}"
        
        if param.annotation is inspect.Parameter.empty:
            type_hint = ""
        else:
            type_name = str(getattr(param.annotation, "__name__", param.annotation))
            type_hint = f" :{type_names.get(type_name, type_name)}"

        usage_hint.append(f"{surround[0]}{param.name}{type_hint}{default_hint}{surround[1]}")
    
    return " ".join(usage_hint)

class Bot(commands.AutoBot):
    def __init__(self, client_id, client_secret, bot_id, prefix:str|Callable[[Self, twitchio.ChatMessage], str], subs:list[twitchio.eventsub.SubscriptionPayload]):
        super().__init__(
            client_id=client_id,
            client_secret=client_secret,
            bot_id=bot_id,
            prefix=prefix,
            subscriptions=subs,
        )
        self.links_commands:set[str] = set()
        self.subs = subs

    def update_link_commands(self):
        def newfunc(name:str):
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
        
        configs = config.read()
        if "Links" in configs:
            links = configs["Links"]
            if isinstance(links, dict):
                sym_difference = self.links_commands ^ set(links.keys()) #values that aren't in both sets
                for name in sym_difference:
                    if name in links:
                        cb = newfunc(name)
                        self.add_command(commands.Command(name=name, callback=cb))
                        annotate_info[name] = CommandAnnotation(inspect.signature(cb), cb.__doc__)
                        self.links_commands.add(name)
                    elif name in self.links_commands:
                        self.remove_command(name)
                        self.links_commands.remove(name)
                        if name in annotate_info:
                            del annotate_info[name]
                return
        for name in self.links_commands:
            self.remove_command(name)

    async def setup_hook(self):
        self.add_listener(self.event_message)
        self.add_listener(self.event_custom_redemption_add)
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
        for name, c in self.commands.items():
            a = _annotate_pre.get(c.callback, None)
            if a is not None:
                annotate_info[name] = a
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
        print("twitch bot ready")

    async def event_message(self, message:twitchio.ChatMessage) -> None:      
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"<{message.broadcaster}> {message.chatter}: {message.text}")
        if message.chatter.id == self.bot_id:
            return
        self.update_link_commands()
        await self.process_commands(message)

    async def event_command_error(self, payload:commands.CommandErrorPayload):
        if isinstance(payload.exception, commands.ArgumentError):
            await payload.context.send("Bad command usage. Use !help <command_name> to view command usage details.")
            print("command error:", type(payload.exception).__name__, payload.exception)

    async def event_custom_redemption_add(self, payload:twitchio.ChannelPointsRedemptionAdd):
        ... #TODO determine which reward was redeemed and handle it
        print(payload.reward.id, payload.reward.title, payload.reward, payload.user, payload.broadcaster)


class CoreComponent(commands.Component):
    def __init__(self, bot:Bot):
        self.bot = bot

    @commands.command(name="help")
    @annotate()
    async def help_command(self, ctx:commands.Context, command_name:str=None):
        """Lists and describes commands."""
        if command_name is None:
            #exclude commands that user does not meet requirements for
            names = [name for name in bot.commands.keys() if (a := annotate_info.get(name, None)) is None or a.meets_requirements(ctx.author)]
            await ctx.send("Commands: " + ", ".join(names))
        elif command_name not in bot.commands:
            await ctx.send(f"Command {command_name} does not exist.")
        else:
            a = annotate_info.get(command_name, None)
            if a is None:
                await ctx.send(f"Command {command_name} has no help info.")
            elif not a.meets_requirements(ctx.author):
                await ctx.send(f"You cannot use this command.")
            else:
                signature = get_command_signature(ctx.prefix, command_name, a)
                r = []
                if a.doc:
                    r.append(a.doc)
                r.append(f"Usage: {signature}")
                await ctx.send(" ".join(r))

    @commands.command(name="links")
    @annotate()
    async def links_command(self, ctx:commands.Context):
        """Lists names of all link commands."""
        if bot.links_commands:
            await ctx.send(", ".join(name for name in bot.links_commands))

    @commands.command(name="pload")
    @annotate(requires_moderator=True)
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

    @commands.command(name="punload")
    @annotate(requires_moderator=True)
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
        subs.append(twitchio.eventsub.ChatMessageSubscription(broadcaster_user_id=user.id, user_id=bot_id))
        if user.broadcaster_type in ("affiliate", "partner"):
            subs.append(twitchio.eventsub.ChannelPointsRedeemAddSubscription(broadcaster_user_id=user.id))

    bot = Bot(client_id, client_secret, bot_id, c["Prefix"], subs)

    if old_bot is not None:
        old_bot.close()
        for cog in old_bot._components.values():
            bot.add_component(cog)
        for command in old_bot._commands.values():
            bot.add_command(command)
        bot.__modules.update(old_bot.__modules)

    return bot


def ws_on_open(ws):
    print("connected to events socket")

def ws_on_message(ws, msg:str|bytearray|memoryview):
    if isinstance(msg, memoryview):
        msg = msg.tobytes()
    print("events socket message:", msg)
    data = json.loads(msg)
    event = events.Event(**data)
    events.handle_event(event)

def ws_on_error(ws, e:Exception):
    print(f"events socket error ({type(e).__name__}):")
    traceback.print_exception(e)

def ws_on_close(ws, status_code, msg:str|bytearray|memoryview):
    print("disconnected from events socket")

def ws_run():
    try:
        ws.run_forever()
    except KeyboardInterrupt:
        pass

async def main():
    await bot.start(load_tokens=False)

if __name__ == "__main__":
    addr, config_path, pconfig_path = get_args()
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
        f"{API_WS_ENDPOINT}/events",
        on_open=ws_on_open, on_message=ws_on_message,
        on_error=ws_on_error, on_close=ws_on_close
    )

    print("reading plugin list")
    plugin_list = plugins.read_plugin_data(pconfig_path)
    plugin_enabled_count = sum(1 for plugin in plugin_list.values() if plugin.module is not None)
    print("read", len(plugin_list), "plugins with", plugin_enabled_count, "enabled plugins")
    print("generating plugin load order")
    load_order = plugins.generate_load_order(plugin_list)
    print("loading enabled plugins")
    for plugin_name in load_order:
        plugin = plugin_list[plugin_name]
        if plugin.module is not None and plugin.startup_load:
            plugin.twitch_bot_load(plugins.TwitchBotLoadEvent(plugin_list, plugin, pconfig_path, True, bot))
    print("loaded plugins")
    plugins.shared_plugins_list = plugin_list

    print("starting events socket connection")
    ws_thread = threading.Thread(target=ws_run)
    ws_thread.start()

    e = None
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("^C")
    except Exception as _e:
        traceback.print_exception(_e)
        e = _e

    print("unloading enabled plugins")
    for plugin in plugin_list.values():
        if plugin.module is not None:
            plugin.twitch_bot_unload(plugins.TwitchBotUnloadEvent(plugin_list, plugin, True, e))
    print("unloaded plugins")

    ws.close()
    ws_thread.join()
