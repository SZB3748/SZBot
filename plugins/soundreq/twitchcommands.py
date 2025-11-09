import aiohttp
from datetime import datetime, timedelta
from twitchio.ext import commands
from twitchbot import annotate, API_ENDPOINT, ratelimit

REQUEST_SOUND_RATELIMIT_DURATION = timedelta(minutes=1)

async def request_sound_limited(ctx:commands.Context, time:datetime):
    duration = (REQUEST_SOUND_RATELIMIT_DURATION - (datetime.now() - time)).total_seconds()
    await ctx.send(f"{ctx.author.mention} wait {duration} seconds before using this command")

REQUEST_SOUND_CMD = "sound"
@ratelimit(5, REQUEST_SOUND_RATELIMIT_DURATION, limited_callback=request_sound_limited)
@annotate(command_name=REQUEST_SOUND_CMD)
async def request_sound(ctx:commands.Context, name:str):
    """Requests that the song with the given name be played."""
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_ENDPOINT}/soundreq/request", data={"key": name, "user":ctx.author.name, "channel":ctx.channel.name}) as r:
            if not r.ok:
                await ctx.send("Failed to request for sound to be played.")

@annotate()
async def list_sounds(ctx:commands.Context):
    """List names of all available sounds."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_ENDPOINT}/soundreq/list") as r:
            if r.ok:
                data = await r.json()
                if isinstance(data, dict):
                    await ctx.send(f"Sounds: {", ".join(data.keys())}")
            else:
                await ctx.send("Failed to get sound list.")


command_list = {
    REQUEST_SOUND_CMD: request_sound,
    "listsounds": list_sounds
}

def add_commands(botinstance:commands.Bot):
    for name, func in command_list.items():
        botinstance.add_command(commands.Command(name=name, callback=func, aliases=[], bypass_global_guards=False))

def remove_commands(botinstance:commands.Bot):
    for name in command_list.keys():
        botinstance.remove_command(name)