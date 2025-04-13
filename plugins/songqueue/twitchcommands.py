import aiohttp
from twitchio.ext import commands
from twitchbot import API_ENDPOINT

async def current_song(ctx:commands.Context):
    """Gets info on the song that's currently playing."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_ENDPOINT}/music/queue") as r:
            if r.ok:
                data = await r.json()
                if isinstance(data, dict):
                    current = data.get("current", None)
                    if isinstance(current, dict):
                        await ctx.send(f"Currently Playing: {current["title"]} ({current["duration"]})  https://youtube.com/watch?v={current["id"]}")
                        return
                await ctx.send("No song is currently playing")
            else:
                await ctx.send("Failed to get song info")

async def add_song(ctx:commands.Context, url:str):
    """Adds the song at the given youtube link to the song queue."""
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_ENDPOINT}/music/queue/push", data={"url": url}) as r:
            if r.ok:
                text = await r.text()
                print("added song", text)
                await ctx.send(f"Added song (position {text})")
            elif r.status == 403:
                text = await r.text()
                print("push request for banned song", text)
                return await ctx.send(f"Song is banned")
            else:
                await ctx.send("Failed to add song")


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
                print(f"skipped {text} songs (purge={purge})")
                await ctx.send(f"Skipped {text} songs")
            else:
                await ctx.send("Failed to skip song")


async def pause_song(ctx:commands.Context):
    """Pauses the current song."""
    if not ctx.author.is_mod:
        return
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_ENDPOINT}/music/playerstate", data={"state": "pause"}) as r:
            if r.ok:
                await ctx.send("Paused")
            else:
                await ctx.send("Failed to pause")


async def play_song(ctx:commands.Context):
    """Resumes playing the current song."""
    if not ctx.author.is_mod:
        return
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_ENDPOINT}/music/playerstate", data={"state": "play"}) as r:
            if r.ok:
                await ctx.send("Resumed Play")
            else:
                await ctx.send("Failed to resume play")


async def music_persistence(ctx:commands.Context, state:bool=True):
    """Changes the persistence state of the music overlay."""
    if not ctx.author.is_mod:
        return
    if isinstance(state, bool):
        async with aiohttp.ClientSession() as session:
            await session.post(f"{API_ENDPOINT}/music/overlay/persistent", data={"value": str(state).lower()})
    else:
        await ctx.send("Invalid music persistent state (true/false)")


async def btrack(ctx:commands.Context, url:str=None, index:int=None):
    """Controls the queue's B-Track."""
    if not ctx.author.is_mod:
        return
    
    async with aiohttp.ClientSession() as session:
        if url is None:
            async with session.get(f"{API_ENDPOINT}/music/b-track") as r:
                if r.ok:
                    j = await r.json()
                    if isinstance(j, dict):
                        url = j.get("url", None)
                        if url is not None:
                            await ctx.send(url)
                            return
                    await ctx.send("No B-Track set")
                else:
                    await ctx.send("Failed to get B-Track status")
        else:
            d = {}
            if index is not None:
                d["index"] = int(index)
            if url != "~":
                d["url"] = url
            await session.post(f"{API_ENDPOINT}/music/b-track", data=d)


async def ban_song(ctx:commands.Context, id:str):
    """Ban the given song ID. Also extracts the ID from a youtube link."""
    if not ctx.author.is_mod:
        return

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_ENDPOINT}/music/blacklist", data={"id": id}) as r:
            if r.ok:
                await ctx.send("Banned song")
            else:
                await ctx.send("Failed to ban song")

command_list = {
    "currentsong": current_song,
    "addsong": add_song,
    "skipsong": skip_song,
    "pausesong": pause_song,
    "playsong": play_song,
    "musicpersist": music_persistence,
    "btrack": btrack,
    "bansong": ban_song
}

def add_commands(botinstance:commands.Bot):
    for name, func in command_list.items():
        botinstance.add_command(commands.Command(name=name, func=func, aliases=None, instance=None, no_global_checks=False))

def remove_commands(botinstance:commands.Bot):
    for name in command_list.keys():
        botinstance.remove_command(name)