import actions
import aiohttp
import argparse
import asyncio
import base64
import command_triggers
import config
from datetime import datetime, timedelta
import inspect
import json
import os
import pickle
import plugins
import rewards
from simple_websocket.errors import ConnectionClosed
import threading
import traceback
from typing import Awaitable, Callable, Self
import twitchio
from twitchio.ext import commands
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
    "user:write:chat"
}

OAUTH_CHANNEL_SCOPES:set[str] = {
    "user:read:chat",
    "user:bot",
    "channel:bot",
    "channel:manage:redemptions"
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
        self._callback_command_triggers:dict[str, command_triggers.CallbackCommandTrigger] = {}
        self._callback_redeem_handlers:dict[rewards.RewardIdentifierKey, rewards.CallbackRedeemHandler] = {}
        self.command_triggers:dict[str, command_triggers.CommandTrigger] = {}
        self.redeem_handlers:dict[rewards.RewardIdentifierKey, rewards.RedeemHandler] = {}
        self.subs = subs
        self.use_core_commands = use_core_commands
        self._loop = None

    def add_command(self, command:command_triggers.CommandTrigger|commands.Command):
        if isinstance(command, command_triggers.CommandTrigger):
            self.command_triggers[command.name] = command
            if isinstance(command, command_triggers.CallbackCommandTrigger):
                self._callback_command_triggers[command.name] = command
            command = command.to_twitch_command()
        return super().add_command(command)
    
    def remove_command(self, name:str|command_triggers.CommandTrigger):
        if isinstance(name, command_triggers.CommandTrigger):
            name = name.name
        command = self.command_triggers.pop(name, None)
        if isinstance(command, command_triggers.CallbackCommandTrigger) and name in self._callback_command_triggers:
            del self._callback_command_triggers[name]
        return super().remove_command(name)
    
    def add_redeem_handler(self, handler:rewards.RedeemHandler):
        if isinstance(handler, rewards.CallbackRedeemHandler):
            self._callback_redeem_handlers[handler.identifier] = handler
        self.redeem_handlers[handler.identifier] = handler
    
    def remove_redeem_handler(self, identifier:tuple[str, str]|rewards.RewardIdentifier):
        rh = self.redeem_handlers.pop(identifier,None)
        if isinstance(rh, rewards.CallbackRedeemHandler) and identifier in self._callback_redeem_handlers:
            del self._callback_redeem_handlers[identifier]

    def _get_redeem_handlers(self, payload:twitchio.ChannelPointsRedemptionAdd)->tuple[rewards.RedeemHandler|None, ...]:
        pair_id = (payload.reward.id, rewards.IDEN_TYPE_ID)
        pair_title = (payload.reward.title, rewards.IDEN_TYPE_TITLE)
        return self.redeem_handlers.get(pair_id,None), self.redeem_handlers.get(pair_title,None)

    def sync_commands(self):
        loaded_commands = command_triggers.load_command_triggers()
        cmd_difference = set(self.command_triggers.keys()) ^ set(loaded_commands.keys())
        for name in cmd_difference:
            if name in loaded_commands:
                self.add_command(loaded_commands[name])
            else: #name in self.command_triggers
                cmd = self.command_triggers[name]
                if isinstance(cmd, command_triggers.CallbackCommandTrigger):
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
            assert isinstance(cmd, command_triggers.ActionCommandTrigger)
            cmd.update(lcmd)

    
    def sync_redeem_handlers(self):
        loaded_redeems = rewards.load_redeem_handlers()
        rh_difference = set(self.redeem_handlers.keys()) ^ set(loaded_redeems.keys())
        for iden in rh_difference:
            if iden in loaded_redeems:
                self.add_redeem_handler(loaded_redeems[iden])
            else: #name in self.redeem_handlers
                rh = self.redeem_handlers[iden]
                if isinstance(rh, rewards.CallbackRedeemHandler):
                    continue
                crh =self._callback_redeem_handlers.get(iden,None)
                if crh is None:
                    del self.redeem_handlers[iden]
                else:
                    self.redeem_handlers[iden] = crh

    def update_link_commands(self):
        configs = config.read()
        if "Links" in configs:
            links:dict[str] = configs["Links"]
            if isinstance(links, dict):
                sym_difference = self.links_commands ^ set(links.keys()) #values that aren't in both sets
                for name in sym_difference:
                    if name in links:
                        cb = _link_command_newfunc(name)
                        ct = command_triggers.CallbackCommandTrigger.new(cb, name)
                        self.add_command(ct)
                        self.links_commands.add(name)
                    else: #name in self.links_commands
                        self.remove_command(name)
                        self.links_commands.remove(name)
                return
        for name in self.links_commands:
            self.remove_command(name)

    async def setup_hook(self):
        self.add_listener(self.event_message)
        self.add_listener(self.event_custom_redemption_add)
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
        bot.sync_redeem_handlers()

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
        else:
            traceback.print_exception(payload.exception)

    async def event_custom_redemption_add(self, payload:twitchio.ChannelPointsRedemptionAdd):
        id_handler, title_handler = self._get_redeem_handlers(payload)

        if id_handler and title_handler and id_handler is not title_handler:
            ... #TODO exception can't have two different redemption handlers for the same reward
        
        handler = id_handler or title_handler
        if handler:
           c = handler.handle(self, payload)
           if inspect.isawaitable(c):
               await c

class CoreComponent(commands.Component):
    def __init__(self, bot:Bot):
        self.bot = bot
        for attr in type(self).__dict__.values():
            if isinstance(attr, command_triggers.CallbackCommandTrigger):
                self.bot.add_command(command_triggers.CallbackCommandTrigger(
                    attr.name,
                    attr.description,
                    attr.signature,
                    attr.permissions,
                    attr.callback,
                    bind=self
                ))

    @command_triggers.CallbackCommandTrigger.create("help")
    async def help_command(self, ctx:commands.Context, command_name:str=None):
        """Lists and describes commands."""
        self.bot.sync_commands()
        command_data = command_triggers.load_commands()

        if command_name is None:
            #exclude commands that user does not meet requirements for
            names = []
            for name, ct in self.bot.command_triggers.items():
                if isinstance(ct, command_triggers.CallbackCommandTrigger):
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
                if isinstance(ct, command_triggers.CallbackCommandTrigger):
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


    @command_triggers.CallbackCommandTrigger.create("links")
    async def links_command(self, ctx:commands.Context):
        """Lists names of all link commands."""
        if bot.links_commands:
            await ctx.send(", ".join(name for name in bot.links_commands))

    @command_triggers.CallbackCommandTrigger.create("pload", permissions=command_triggers.CommandPermissions(requires_moderator=True))
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

    @command_triggers.CallbackCommandTrigger.create("punload", permissions=command_triggers.CommandPermissions(requires_moderator=True))
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
        bot._callback_command_triggers.update(old_bot._callback_command_triggers)
        bot._callback_redeem_handlers.update(old_bot._callback_redeem_handlers)
        bot.links_commands.update(old_bot.links_commands)
        bot.command_triggers.update(old_bot.command_triggers)
        bot.redeem_handlers.update(old_bot.redeem_handlers)
        bot.use_core_commands = old_bot.use_core_commands
    return bot


_arl_tasks:dict[uuid.UUID, asyncio.Task] = {}
_arl_tasks_lock = threading.Lock()

async def _action_runner_local_task(ws:websocket.WebSocket, task_id:uuid.UUID, scripts:list[tuple[uuid.UUID, actions.tronix.Script, *tuple]]):
    results = await actions.run_scripts(*scripts)
    ws.send(json.dumps({
        "instruction": "done",
        "scripts": {
            str(uid): success
            for uid, success, *_ in results
        }
    }))
    with _arl_tasks_lock:
        _arl_tasks.pop(task_id,None)

def ws_on_open(ws):
    print("connected to script env switch")

def ws_on_reconnect(ws):
    print("reconnected to script env switch")

def ws_on_message(ws:websocket.WebSocket, msg:str|bytearray|memoryview):
    if isinstance(msg, memoryview):
        msg = msg.tobytes()
    data = json.loads(msg)
    if not isinstance(data, dict):
        return
    instruction = data["instruction"]
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
                elif env == actions.current_environment_name:
                    script = sdata["script"]
                    if isinstance(script, dict):
                        uid = uuid.UUID(sdata["uid"])
                        scope = pickle.loads(base64.b64decode(script["scope"]))
                        s = tronix.Script(script["content"], scope)
                        add_run.append((uid, s, env))
                else:
                    uid = uuid.UUID(sdata["uid"])
                    script = sdata["script"]
                    with actions._env_switch_queue_lock:
                        q = actions._env_switch_queue.get(env,None)
                        if q is None:
                            actions._env_switch_queue[env] = q = []
                        q.append((uid, env, script, actions._env_switch_done_entry())) #NOTE idk if i wanna be making a _env_switch_done_entry here
            if add_run:
                with _arl_tasks_lock:
                    task_id = uuid.uuid4()
                    _arl_tasks[task_id] = asyncio.ensure_future(_action_runner_local_task(ws, task_id, add_run), bot._loop)

    elif instruction == "done":
        scripts = data.get("scripts",None)
        if isinstance(scripts, dict):
            for id_s, success in scripts.items():
                uid = uuid.UUID(id_s)
                de = actions._env_switch_done.get(uid,None)
                if de is not None:
                    de.mark_done(bool(success))
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

def ws_run():
    try:
        ws.run_forever(reconnect=5)
    except KeyboardInterrupt:
        pass

async def main():
    await bot.start(load_tokens=False, save_tokens=False)

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
        f"{API_WS_ENDPOINT}/api/actions/script/env-switch?name={actions.current_environment_name}",
        on_open=ws_on_open, on_message=ws_on_message,
        on_error=ws_on_error, on_close=ws_on_close,
        on_reconnect=ws_on_reconnect
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

    if components:
        commands_mode = components.get(plugins.TWITCHBOT_COMPONENT_COMMANDS, plugins.COMPONENT_MODE_NORMAL)
        tronix_mode = components.get(plugins.TWITCHBOT_COMPONENT_TRONIX, plugins.COMPONENT_MODE_NORMAL)
    else:
        commands_mode = tronix_mode = plugins.COMPONENT_MODE_NORMAL
    
    bot.use_core_commands = commands_mode == plugins.COMPONENT_MODE_NORMAL

    assert tronix_mode != plugins.COMPONENT_MODE_REMOTE, "Twitchbot tronix has no remote mode."
    if tronix_mode == plugins.COMPONENT_MODE_NORMAL:
        print("loading script environment")
        import tronix.script_builtins, tronix_twitch_integrations
        tronix.script_builtins.activate()
        tronix_twitch_integrations.activate()
        print("loaded script environment")

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
