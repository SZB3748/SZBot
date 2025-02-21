import asyncio
import config
import requests
import twitchio
import traceback
from twitchio.ext import commands
from urllib.parse import quote

TOKEN_REFRESH_ENDPOINT = "https://id.twitch.tv/oauth2/token"

class Bot(commands.Bot):
    def __init__(self, configs:dict[str]):
        super().__init__(
            token=configs["Token"],
            prefix=configs["Prefix"],
            client_secret=configs["Client-Secret"],
            initial_channels=configs["Channels"],
        )

    async def event_command_error(self, ctx: commands.Context, err: Exception):
        if isinstance(err, (commands.CommandNotFound, commands.MissingRequiredArgument, commands.ArgumentParsingFailed)):
            print(err)
        else:
            traceback.print_exception(err)

    async def event_token_expired(self):
        configs = config.read()
        r = requests.post(f"{TOKEN_REFRESH_ENDPOINT}?client_id={configs["Client-Id"]}&client_secret={configs["Client-Secret"]}&grant_type=refresh_token&refresh_token={quote(configs["Refresh-Token"])}")
        if r.ok:
            j = r.json()
            token:str = j["access_token"]
            config.write(config_updates={
                "Token": token,
                "Refresh-Token": j["refresh_token"]
            })
            return token
        else:
            print(r.text)
            if "Token" in configs:
                del configs["Token"]
            del configs["Refresh-Token"]
            config.write(new_configs=configs)
            return None

#set up the bot
def init_bot():    
    configs = config.read()
    return Bot(configs)

async def main():
    try:
        await bot.start()
    except twitchio.errors.AuthenticationError as e:
        print(e)
        token = await bot.event_token_expired()
        if token is None:
            print("Failed to refresh token. Make sure Token is removed from config,json and run the main script to generate a new token.")
        else:
            print("New token generated. Rerun bot script.")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    bot = init_bot()

    @bot.event()
    async def event_ready():
        print("bot running")

    @bot.command(name="addsong")
    async def add_song(ctx:commands.Context, url:str):
        r = requests.post("http://localhost:8080/api/music/queue/push", data={"url": url})
        if r.ok:
            print(f"Added song ({r.text})")
        else:
            print("Failed to add song")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
