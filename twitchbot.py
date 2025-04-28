import asyncio
import config
from datetime import datetime, timedelta
import events
import inspect
import json
import plugins
import requests
import threading
import traceback
from typing import Awaitable, Callable
import twitchio
from twitchio.ext import commands
from urllib.parse import quote
import websocket

API_BASE = "localhost:6742/api"
API_ENDPOINT = f"http://{API_BASE}"
API_WS_ENDPOINT = f"ws://{API_BASE}"
TOKEN_REFRESH_ENDPOINT = "https://id.twitch.tv/oauth2/token"

def get_prefix(bot:commands.Bot, message:twitchio.Message):
    configs = config.read()
    return configs["Prefix"]

def ratelimit(max_times:int, duration:timedelta, limited_callback:Callable[[commands.Context, datetime], Awaitable[None]]|None=None):
    users:dict[twitchio.PartialChatter|twitchio.Chatter, list[datetime]] = {}

    def decor(f:Callable[..., Awaitable]):
        async def wrapper(ctx:commands.Context, *args, **kwargs):
            if True or not ctx.author.is_mod:
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
    "chat:read",
    "chat:edit",
    "user:read:chat",
    "user:write:chat",
    "user:bot",
    "channel:bot"
}

def get_command_signature(prefix:str, cmd:commands.Command)->str:
    cmd_func = cmd._callback

    spec = inspect.signature(cmd_func)
    usage_hint = [prefix + cmd.name]
    if "ctx" in spec.parameters:
        param_items = list(spec.parameters.keys())
        start_index = param_items.index("ctx") + 1
    else:
        start_index = 0

    params = list(spec.parameters.values())
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

class Bot(commands.Bot):
    def __init__(self, configs:dict[str], oauth:dict[str], links_commands:set[str]|None=None):
        super().__init__(
            token=oauth["Token"],
            prefix=get_prefix,
            client_secret=oauth["Client-Secret"],
            initial_channels=configs.get("Channels", None) or [],
        )
        self.links_commands:set[str] = set() if links_commands is None else set(links_commands)

    def update_link_commands(self):
        configs = config.read()
        if "Links" in configs:
            links = configs["Links"]
            if isinstance(links, dict):
                sym_difference = self.links_commands ^ set(links.keys()) #values that aren't in both sets
                for name in sym_difference:
                    if name in links:
                        async def func(ctx:commands.Context):
                            configs = config.read()
                            if "Links" not in configs:
                                return
                            links = configs["Links"]
                            if isinstance(links, dict) and name in links:
                                link = links[name]
                                if isinstance(link, str):
                                    await ctx.send(link)
                        func.__doc__ = "Sends the accociated text in chat."
                        self.add_command(commands.Command(name=name, func=func, aliases=None, instance=None, no_global_checks=False))
                        self.links_commands.add(name)
                    elif name in self.links_commands:
                        self.remove_command(name)
                        self.links_commands.remove(name)
                return
        for name in self.links_commands:
            self.remove_command(name)

    async def event_command_error(self, ctx: commands.Context, err: Exception):
        if isinstance(err, (commands.CommandNotFound, commands.MissingRequiredArgument, commands.ArgumentParsingFailed)):
            await ctx.send("Bad command usage. Use !help <command_name> to view command usage details.")
            print(err)
        else:
            traceback.print_exception(err)

    async def event_token_expired(self):
        oauth = config.read(path=config.OAUTH_TWITCH_FILE)
        r = requests.post(f"{TOKEN_REFRESH_ENDPOINT}?client_id={oauth["Client-Id"]}&client_secret={oauth["Client-Secret"]}&grant_type=refresh_token&refresh_token={quote(oauth["Refresh-Token"])}")
        if r.ok:
            j = r.json()
            token:str = j["access_token"]
            config.write(config_updates={
                "Token": token,
                "Refresh-Token": j["refresh_token"]
            }, path=config.OAUTH_TWITCH_FILE)
            return token
        else:
            print(r.text)
            if "Token" in oauth:
                del oauth["Token"]
            del oauth["Refresh-Token"]
            config.write(new_configs=oauth, path=config.OAUTH_TWITCH_FILE)
            return None
        
    async def event_ready(self):
        print("bot running")

    async def event_message(self, message:twitchio.Message):
        if message.author is None: #bot message
            return
        
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"{message.author}: {message.content}")
        self.update_link_commands()
        await self.handle_commands(message)


#set up the bot
def init_bot(old_bot:Bot|None=None):
    configs = config.read()
    oauth = config.read(path=config.OAUTH_TWITCH_FILE)

    if not ("Token" in oauth and "Client-Secret" in oauth and "Prefix" in configs):
        return None

    newbot = Bot(configs, oauth)
    if old_bot is not None:
        for cog in old_bot._cogs.values():
            newbot.add_cog(cog)
        for command in old_bot._commands.values():
            newbot.add_command(command)
        newbot._modules.update(old_bot._modules)
    return newbot

def ws_on_open(ws):
    print("connected to events socket")

def ws_on_message(ws, msg:str|bytes):
    print("events socket message:", msg)
    data = json.loads(msg)
    event = events.Event(**data)
    events.handle_event(event)

def ws_on_error(ws, e:Exception):
    print(f"events socket error ({type(e).__name__}): {e}")

def ws_on_close(ws, status_code, msg:str|bytes):
    print("disconnected from events socket")

def ws_run():
    try:
        ws.run_forever()
    except KeyboardInterrupt:
        pass

async def main(retry:bool=True):
    global bot
    try:
        await bot.start()
    except twitchio.errors.AuthenticationError as e:
        print(e)
        if not retry:
            return
        token = await bot.event_token_expired()
        if token is None:
            print("Failed to refresh token. Make sure Token is removed from config.json and run the main script to generate a new token.")
        else:
            print("New token generated. Attempting to start bot again.")
            bot = init_bot(old_bot=bot)
            await main(retry=False)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    bot = init_bot()
    if bot is None:
        print("You must run main.py first to make sure your oauth_twitch.json file is fine.\nAlso, make sure to make a config.json file with your bot's \"Prefix\".")
        exit(-1)

    ws = websocket.WebSocketApp(
        f"{API_WS_ENDPOINT}/events",
        on_open=ws_on_open, on_message=ws_on_message,
        on_error=ws_on_error, on_close=ws_on_close
    )

    @bot.command(name="help")
    async def help_command(ctx:commands.Context, command_name:str=None):
        """Lists and describes commands."""
        if command_name is None:
            await ctx.send("Commands: " + ", ".join(bot.commands.keys()))
        else:
            cmd = bot.commands.get(command_name, None)
            if isinstance(cmd, commands.Command):
                signature = get_command_signature(ctx.prefix, cmd)
                r = []
                doc = cmd._callback.__doc__
                if doc:
                    r.append(doc)
                r.append(f"Usage: {signature}")
                await ctx.send(" ".join(r))
            else:
                await ctx.send(f"Command {command_name} does not exist.")

    @bot.command(name="links")
    async def links_command(ctx:commands.Context):
        """Lists names of all link commands."""
        if bot.links_commands:
            await ctx.send(", ".join(name for name in bot.links_commands))


    print("reading plugin list")
    plugin_list = plugins.read_plugin_data()
    plugin_enabled_count = sum(1 for plugin in plugin_list.values() if plugin.module is not None)
    print("read", len(plugin_list), "plugins with", plugin_enabled_count, "enabled plugins")
    print("generating plugin load order")
    load_order = plugins.generate_load_order(plugin_list)
    print("loading enabled plugins")
    for plugin_name in load_order:
        plugin = plugin_list[plugin_name]
        if plugin.module is not None:
            plugin.twitch_bot_load((plugin_list, plugin, True, bot))
    print("loaded plugins")

    print("starting events socket connection")
    ws_thread = threading.Thread(target=ws_run)
    ws_thread.start()

    loop = asyncio.get_event_loop()
    e = None
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("^C")
    except Exception as _e:
        e = _e

    print("unloading enabled plugins")
    for plugin in plugin_list.values():
        if plugin.module is not None:
            plugin.twitch_bot_unload((plugin_list, plugin, True, e))
    print("unloaded plugins")

    ws.close()
    ws_thread.join()
