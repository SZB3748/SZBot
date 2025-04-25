import aiohttp
import asyncio
from datetime import datetime, timedelta
import events
from twitchio.ext import commands
from twitchbot import API_ENDPOINT, ratelimit

REQUEST_SOUND_RATELIMIT_DURATION = timedelta(minutes=1)

async def request_sound_limited(ctx:commands.Context, time:datetime):
    duration = (REQUEST_SOUND_RATELIMIT_DURATION - (datetime.now() - time)).total_seconds()
    await ctx.send(f"{ctx.author.mention} wait {duration} seconds before using this command")

@ratelimit(5, REQUEST_SOUND_RATELIMIT_DURATION, limited_callback=request_sound_limited)
async def request_sound(ctx:commands.Context, name:str):
    """Requests that the song with the given name be played."""
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_ENDPOINT}/soundreq/request", data={"key": name, "user":ctx.author.name, "channel":ctx.channel.name}) as r:
            if not r.ok:
                await ctx.send("Failed to request for sound to be played.")

async def list_sound(ctx:commands.Context):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_ENDPOINT}/soundreq/list") as r:
            if r.ok:
                data = await r.json()
                if isinstance(data, dict):
                    await ctx.send(f"Sounds: {", ".join(data.keys())}")
            else:
                await ctx.send("Failed to get sound list.")


command_list = {
    "sound": request_sound,
    "listsounds": list_sound
}

def add_commands(botinstance:commands.Bot):
    for name, func in command_list.items():
        botinstance.add_command(commands.Command(name=name, func=func, aliases=None, instance=None, no_global_checks=False))

def remove_commands(botinstance:commands.Bot):
    for name in command_list.keys():
        botinstance.remove_command(name)