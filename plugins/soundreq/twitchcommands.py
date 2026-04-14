import aiohttp
import command_triggers
from datetime import datetime, timedelta
from twitchio.ext import commands
from twitchbot import API_ENDPOINT, Bot, ratelimit

REQUEST_SOUND_RATELIMIT_DURATION = timedelta(minutes=1)

async def request_sound_limited(ctx:commands.Context, time:datetime):
    duration = (REQUEST_SOUND_RATELIMIT_DURATION - (datetime.now() - time)).total_seconds()
    await ctx.send(f"{ctx.author.mention} wait {duration} seconds before using this command")

@command_triggers.CallbackCommandTrigger.create("sound")
@ratelimit(5, REQUEST_SOUND_RATELIMIT_DURATION, limited_callback=request_sound_limited)
@command_triggers.CommandSignature.store()
async def request_sound(ctx:commands.Context, name:str):
    """Requests that the song with the given name be played."""
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_ENDPOINT}/soundreq/request", data={"key": name, "user":ctx.author.name, "channel":ctx.channel.name}) as r:
            if not r.ok:
                await ctx.send("Failed to request for sound to be played.")


@command_triggers.CallbackCommandTrigger.create("listsounds")
async def list_sounds(ctx:commands.Context):
    """List names of all available sounds."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_ENDPOINT}/soundreq/list") as r:
            if r.ok:
                data = await r.json()
                if isinstance(data, dict):
                    await ctx.send(f"Sounds: {", ".join(k for k,v in data.items() if not v.get("hidden",False))}")
            else:
                await ctx.send("Failed to get sound list.")


command_list = [
    request_sound,
    list_sounds
]

def add_commands(botinstance:Bot):
    for ct in command_list:
        botinstance.add_command(ct)

def remove_commands(botinstance:Bot):
    for ct in command_list:
        botinstance.remove_command(ct)