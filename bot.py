import asyncio
import config
from datetime import datetime
import requests
import traceback
import twitchio
from twitchio.ext import commands
from typing import Any, Awaitable, Callable
from urllib.parse import quote

TOKEN_REFRESH_ENDPOINT = "https://id.twitch.tv/oauth2/token"

def get_prefix(bot:commands.Bot, message:twitchio.Message):
    configs = config.read()
    return configs["Prefix"]

class Bot(commands.Bot):
    def __init__(self, configs:dict[str], oauth:dict[str]):
        super().__init__(
            token=oauth["Token"],
            prefix=get_prefix,
            client_secret=oauth["Client-Secret"],
            initial_channels=configs.get("Channels", None) or [],
        )

    async def event_command_error(self, ctx: commands.Context, err: Exception):
        if isinstance(err, (commands.CommandNotFound, commands.MissingRequiredArgument, commands.ArgumentParsingFailed)):
            print(err)
        else:
            traceback.print_exception(err)

    async def event_token_expired(self):
        oauth = config.read(path=config.OAUTH_FILE)
        r = requests.post(f"{TOKEN_REFRESH_ENDPOINT}?client_id={oauth["Client-Id"]}&client_secret={oauth["Client-Secret"]}&grant_type=refresh_token&refresh_token={quote(oauth["Refresh-Token"])}")
        if r.ok:
            j = r.json()
            token:str = j["access_token"]
            config.write(config_updates={
                "Token": token,
                "Refresh-Token": j["refresh_token"]
            }, path=config.OAUTH_FILE)
            return token
        else:
            print(r.text)
            if "Token" in oauth:
                del oauth["Token"]
            del oauth["Refresh-Token"]
            config.write(new_configs=oauth, path=config.OAUTH_FILE)
            return None

#set up the bot
def init_bot():
    configs = config.read()
    oauth = config.read(path=config.OAUTH_FILE)

    if not ("Token" in oauth and "Client-Secret" in oauth and "Prefix" in configs):
        return None

    return Bot(configs, oauth)

async def main():
    try:
        await bot.start()
    except twitchio.errors.AuthenticationError as e:
        print(e)
        token = await bot.event_token_expired()
        if token is None:
            print("Failed to refresh token. Make sure Token is removed from config.json and run the main script to generate a new token.")
        else:
            print("New token generated. Rerun bot script.")
    except KeyboardInterrupt:
        pass


def log_command(f:Callable[..., Awaitable[Any]]):
    async def wrapper(ctx:commands.Context, *args, **kwargs):
        print(datetime.now().strftime("[%Y-%M-%d %H:%M:%S]"), f"{ctx.author}: {ctx.message.content}")
        return await f(ctx, *args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

async def link_command(ctx:commands.Context, name:str):
    configs = config.read()
    if "Links" not in configs:
        return
    links = configs["Links"]
    if isinstance(links, dict) and name in links:
        link = links[name]
        if isinstance(link, str):
            await ctx.send(link)

if __name__ == "__main__":
    bot = init_bot()
    if bot is None:
        print("You must run main.py first to make sure your oauth.json file is fine.\nAlso, make sure to make a config.json file with your bot's \"Prefix\".")
        exit(-1)

    @bot.event()
    async def event_ready():
        print("bot running")

    @bot.command(name="github")
    @log_command
    async def github_link(ctx:commands.Context):
        await link_command(ctx, "github")

    @bot.command(name="discord")
    @log_command
    async def discord_link(ctx:commands.Context):
        await link_command(ctx, "discord")

    @bot.command(name="addsong")
    @log_command
    async def add_song(ctx:commands.Context, url:str):
        r = requests.post("http://localhost:6742/api/music/queue/push", data={"url": url})
        if r.ok:
            print(f"Added song ({r.text})")
        else:
            print("Failed to add song")
    
    @bot.command(name="skipsong")
    @log_command
    async def skip_song(ctx:commands.Context, count:int=1):
        if not ctx.author.is_mod: #also works for broadcaster
            return
        
        count = int(count)
        if count <= 0:
            return
        r = requests.post("http://localhost:6742/api/music/queue/skip", data={"count": count})
        if r.ok:
            print(f"Skipped", r.text, "songs")
        else:
            print("Failed to skip song")

    @bot.command(name="pausesong")
    @log_command
    async def pause_song(ctx:commands.Context):
        if not ctx.author.is_mod:
            return
        r = requests.post("http://localhost:6742/api/music/playerstate", data={"state": "pause"})
        if r.ok:
            print("Paused")
        else:
            print("Failed to pause")

    @bot.command(name="playsong")
    @log_command
    async def play_song(ctx:commands.Context):
        if not ctx.author.is_mod:
            return
        r = requests.post("http://localhost:6742/api/music/playerstate", data={"state": "play"})
        if r.ok:
            print("Paused")
        else:
            print("Failed to pause")


    @bot.command(name="musicpersist")
    @log_command
    async def music_persistence(ctx:commands.Context, state:str="true"):
        if not ctx.author.is_mod:
            return
        state = state.strip().lower()
        if state in ("true", "false"):
            requests.post("http://localhost:6742/api/music/overlay/persistent", data={"value": state})
        else:
            print("Invalid music persistent state (true/false)")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
