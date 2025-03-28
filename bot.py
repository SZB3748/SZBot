import aiohttp
import asyncio
import config
from datetime import datetime
import inspect
import requests
import traceback
import twitchio
from twitchio.ext import commands
from urllib.parse import quote

TOKEN_REFRESH_ENDPOINT = "https://id.twitch.tv/oauth2/token"
API_ENDPOINT = "http://localhost:6742/api"

def get_prefix(bot:commands.Bot, message:twitchio.Message):
    configs = config.read()
    return configs["Prefix"]

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
        self.links_commands = set() if links_commands is None else set(links_commands)

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

if True or __name__ == "__main__":
    bot = init_bot()
    if bot is None:
        print("You must run main.py first to make sure your oauth.json file is fine.\nAlso, make sure to make a config.json file with your bot's \"Prefix\".")
        exit(-1)


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

    @bot.command(name="addsong")
    async def add_song(ctx:commands.Context, url:str):
        """Adds a song to the song queue."""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_ENDPOINT}/music/queue/push", data={"url": url}) as r:
                if r.ok:
                    text = await r.text()
                    print(f"Added song ({text})")
                else:
                    print("Failed to add song")
    
    @bot.command(name="skipsong")
    async def skip_song(ctx:commands.Context, count:int=1, purge:bool=False):
        """Skips songs in the song queue."""
        if not ctx.author.is_mod: #also works for broadcaster
            return
        
        count = int(count)
        if count <= 0:
            return
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_ENDPOINT}/music/queue/skip", data={"count": count, "purge":str(purge).lower()}) as r:
                if r.ok:
                    text = await r.text()
                    print(f"Skipped", text, f"songs (purge={purge})")
                else:
                    print("Failed to skip song")

    @bot.command(name="pausesong")
    async def pause_song(ctx:commands.Context):
        """Pauses the current song."""
        if not ctx.author.is_mod:
            return
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_ENDPOINT}/music/playerstate", data={"state": "pause"}) as r:
                if r.ok:
                    print("Paused")
                else:
                    print("Failed to pause")

    @bot.command(name="playsong")
    async def play_song(ctx:commands.Context):
        """Resumes playing the current song."""
        if not ctx.author.is_mod:
            return
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_ENDPOINT}/music/playerstate", data={"state": "play"}) as r:
                if r.ok:
                    print("Resumed Play")
                else:
                    print("Failed to resume play")


    @bot.command(name="musicpersist")
    async def music_persistence(ctx:commands.Context, state:bool=True):
        """Changes the persistence state of the music overlay."""
        if not ctx.author.is_mod:
            return
        if isinstance(state, bool):
            async with aiohttp.ClientSession() as session:
                await session.post(f"{API_ENDPOINT}/music/overlay/persistent", data={"value": str(state).lower()})
        else:
            print("Invalid music persistent state (true/false)")

    @bot.command(name="btrack")
    async def music_btrack(ctx:commands.Context, url:str=None, index:int=None):
        """Controls the queue's B-Track."""
        if not ctx.author.is_mod:
            return
        
        async with aiohttp.ClientSession() as session:
            if url is None and index is None:
                async with session.get(f"{API_ENDPOINT}/music/b-track") as r:
                    j = await r.json()
                    if isinstance(j, dict):
                        url = j.get("url", None)
                        if url is not None:
                            await ctx.send(url)
                            return
                    await ctx.send("No B-Track set")
            else:
                d = {}
                if index is not None:
                    d["index"] = int(index)
                if url:
                    d["url"] = url
                await session.post(f"{API_ENDPOINT}/music/b-track", data=d)
        

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
