import discord
from discord.ext import commands
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
import re

# Add your Discord user ID here for gclock/gcview/gcunlock authorization
watched_channel = {1077296245569237114, 1316250343444840450}

with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

all_bots = []
watched_users = {}
watched_roles = set()
react_all_servers = {}
token_user_ids = set()
blacklisted_users = {}
locked_gcs = {}

# --- Snipe support ---
last_deleted = {}

def get_lyrics_azlyrics(song_title, artist_name):
    artist = re.sub(r'[^a-z0-9]', '', artist_name.lower())
    title = re.sub(r'[^a-z0-9]', '', song_title.lower())
    url = f"https://www.azlyrics.com/lyrics/{artist}/{title}.html"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        divs = soup.find_all("div")
        for div in divs:
            if div.attrs == {}:
                lyrics = div.get_text(separator="\n").strip()
                return lyrics
    except Exception:
        return None
    return None

def get_lyrics_lyricsfreak(song_title, artist_name):
    artist = re.sub(r'[^a-z0-9]', '', artist_name.lower())
    title = re.sub(r'[^a-z0-9]', '', song_title.lower())
    url = f"https://www.lyricsfreak.com/{artist[0]}/{artist}/{title}-lyrics.html"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        lyrics_div = soup.find("div", class_="lyrictxt js-lyrics js-share-text-content")
        if lyrics_div:
            lyrics = lyrics_div.get_text(separator="\n").strip()
            return lyrics
    except Exception:
        return None
    return None

def get_lyrics(song_title, artist_name):
    lyrics = get_lyrics_azlyrics(song_title, artist_name)
    if lyrics:
        return lyrics
    lyrics = get_lyrics_lyricsfreak(song_title, artist_name)
    if lyrics:
        return lyrics
    return None

async def set_custom_status(token, text):
    url = "https://discord.com/api/v10/users/@me/settings"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    payload = {
        "custom_status": {
            "text": text[:128],
            "emoji_name": None
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, json=payload, headers=headers) as resp:
            return resp.status == 200

async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)

    lyric_task = None
    typer_tasks = {}
    gclock_tasks = {}

    @bot.event
    async def on_message_delete(message):
        # Don't snipe deleted !snipe commands
        if message.content.strip().startswith(f"{bot.command_prefix}snipe"):
            return
        last_deleted[message.channel.id] = message

    @bot.event
    async def on_ready():
        token_user_ids.add(bot.user.id)

    @bot.event
    async def on_message(message):
        if message.author.id in blacklisted_users:
            return
        author_id = message.author.id
        author_roles = {role.id for role in getattr(message.author, "roles", [])}
        should_react = (
            author_id == bot.user.id or
            author_id in token_user_ids or
            author_id in watched_users or
            watched_roles.intersection(author_roles) or
            (message.guild and message.guild.id in react_all_servers)
        )
        if should_react:
            try:
                if author_id in watched_users:
                    emojis = watched_users[author_id]
                elif message.guild and message.guild.id in react_all_servers:
                    emojis = react_all_servers[message.guild.id]
                else:
                    emojis = []
                for emoji in emojis:
                    await message.add_reaction(emoji)
            except:
                pass
        if message.content.startswith("[[SPAMALL_TRIGGER]]::") and message.author != bot.user:
            try:
                _, count, msg = message.content.split("::", 2)
                for _ in range(int(count)):
                    await message.channel.send(msg)
                    await asyncio.sleep(0.1)
            except:
                pass
        if message.guild is None:
            if message.author.id in locked_gcs:
                for gc_id in locked_gcs[message.author.id]:
                    channel = bot.get_channel(gc_id)
                    if channel:
                        try:
                            await channel.add_recipients(message.author)
                        except:
                            pass
        await bot.process_commands(message)

    @bot.command()
    async def snipe(ctx):
        await ctx.message.delete()
        msg = last_deleted.get(ctx.channel.id)
        if msg:
            await ctx.send(f"Last deleted message:\n**{msg.author}:** {msg.content}")
        else:
            await ctx.send("No recently deleted messages!")

    @bot.command()
    async def blacklist(ctx, user_id: int):
        await ctx.message.delete()
        blacklisted_users[user_id] = True
        await ctx.send(f"User {user_id} blacklisted.")

    @bot.command()
    async def unblacklist(ctx, user_id: int):
        await ctx.message.delete()
        blacklisted_users.pop(user_id, None)
        await ctx.send(f"User {user_id} unblacklisted.")

    @bot.command()
    async def react(ctx, user: discord.User, *emojis):
        await ctx.message.delete()
        if not emojis:
            await ctx.send("Provide at least one emoji.")
            return
        watched_users[user.id] = list(emojis)
        await ctx.send(f"Reacting to {user.name} with {''.join(emojis)}")

    @bot.command()
    async def unreact(ctx, user: discord.User):
        await ctx.message.delete()
        watched_users.pop(user.id, None)
        await ctx.send(f"Stopped reacting to {user.name}")

    @bot.command()
    async def watchrole(ctx, role: discord.Role, *emojis):
        await ctx.message.delete()
        watched_roles.add(role.id)
        await ctx.send(f"Watching role {role.name}")

    @bot.command()
    async def unwatchrole(ctx, role: discord.Role):
        await ctx.message.delete()
        watched_roles.discard(role.id)
        await ctx.send(f"Stopped watching role {role.name}")

    @bot.command()
    async def reactall(ctx, server_id: int, *emojis):
        await ctx.message.delete()
        if not emojis:
            await ctx.send("Provide at least one emoji.")
            return
        react_all_servers[server_id] = list(emojis)
        await ctx.send(f"Reacting in server {server_id}")

    @bot.command()
    async def unreactall(ctx, server_id: int):
        await ctx.message.delete()
        react_all_servers.pop(server_id, None)
        await ctx.send(f"Stopped reacting in server {server_id}")

    @bot.command()
    async def spam(ctx, *, args):
        await ctx.message.delete()
        try:
            msg, count = args.rsplit(" ", 1)
            count = int(count)
        except:
            await ctx.send("Usage: !spam <message> <count>")
            return
        for _ in range(count):
            await ctx.send(msg)

    @bot.command()
    async def spamall(ctx, *, args):
        await ctx.message.delete()
        try:
            msg, count = args.rsplit(" ", 1)
            count = int(count)
        except:
            await ctx.send("Usage: !spamall <message> <count>")
            return
        trigger = f"[[SPAMALL_TRIGGER]]::{count}::{msg}"
        await ctx.send(trigger)

    @bot.command()
    async def rpc(ctx, activity_type: str, *, activity_message: str):
        await ctx.message.delete()
        types = {
            "playing": discord.Game,
            "streaming": discord.Streaming,
            "listening": discord.Activity,
            "watching": discord.Activity,
            "competing": discord.Activity
        }
        activity_type = activity_type.lower()
        if activity_type == "streaming":
            activity = discord.Streaming(name=activity_message, url="https://twitch.tv/yourchannel")
        elif activity_type in types:
            if activity_type == "playing":
                activity = types[activity_type](name=activity_message)
            else:
                enum_type = getattr(discord.ActivityType, activity_type)
                activity = discord.Activity(type=enum_type, name=activity_message)
        else:
            await ctx.send("Invalid activity type.")
            return
        await bot.change_presence(activity=activity)
        await ctx.send(f"Status set to {activity_type} {activity_message}")

    @bot.command()
    async def statusall(ctx, activity_type: str, *, activity_message: str):
        await ctx.message.delete()
        for b in all_bots:
            try:
                if activity_type == "streaming":
                    activity = discord.Streaming(name=activity_message, url="https://twitch.tv/yourchannel")
                elif activity_type == "playing":
                    activity = discord.Game(name=activity_message)
                else:
                    enum_type = getattr(discord.ActivityType, activity_type)
                    activity = discord.Activity(type=enum_type, name=activity_message)
                await b.change_presence(activity=activity)
            except:
                pass
        await ctx.send(f"All bots updated to {activity_type} {activity_message}")

    @bot.command()
    async def typer(ctx, channel_id: int):
        await ctx.message.delete()
        channel = bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Invalid channel ID.")
            return
        await ctx.send(f"Typing forever in <#{channel_id}> (use !stoptyper to stop)")
        task = asyncio.create_task(typing_loop(channel))
        typer_tasks[ctx.author.id] = task

    async def typing_loop(channel):
        while True:
            async with channel.typing():
                await asyncio.sleep(5)

    @bot.command()
    async def stoptyper(ctx):
        await ctx.message.delete()
        task = typer_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            typer_tasks.pop(ctx.author.id, None)
            await ctx.send("Typing stopped.")
        else:
            await ctx.send("No active typer.")

    @bot.command()
    async def purge(ctx, amount: int, user: discord.User = None):
        await ctx.message.delete()
        if user is None:
            user = ctx.author
        deleted = 0
        async for msg in ctx.channel.history(limit=1000):
            if deleted >= amount:
                break
            if msg.author == user:
                try:
                    await msg.delete()
                    deleted += 1
                except:
                    pass
        await ctx.send(f"Deleted {deleted} messages from {user.name}.", delete_after=5)

    @bot.command(name="h")
    async def help_cmd(ctx):
        await ctx.message.delete()
        help_message = (
            "**Commands:**\n"
            "\n"
            "**🔹 Reacting:**\n"
            "`!react`, `!unreact`, `!reactall`, `!unreactall`, `!watchrole`, `!unwatchrole`\n"
            "\n"
            "**🔹 Spamming:**\n"
            "`!spam`, `!spamall`, `!massdmspam`, `!webhookspam`\n"
            "\n"
            "**🔹 Status:**\n"
            "`!rpc`, `!statusall`, `!typer`, `!stoptyper`\n"
            "\n"
            "**🔹 Moderation:**\n"
            "`!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n"
            "\n"
            "**🔹 Lyrics:**\n"
            "`!lyrics <Song> - <Artist>`, `!stoplyrics`\n"
            "\n"
            "**🔹 Group Chat Lock:**\n"
            "`!gclock <@user|all> <gc_id>`, `!gcunlock <@user|all> <gc_id>`, `!gcview <gc_id>`\n"
            "\n"
            "*:3*"
        )
        await ctx.send(help_message)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")

    @bot.command()
    async def lyrics(ctx, *, song: str):
        await ctx.message.delete()
        nonlocal lyric_task
        if " - " not in song:
            await ctx.send("Format: Song Title - Artist")
            return
        song_name, artist_name = song.split(" - ", 1)
        lyrics = get_lyrics(song_name, artist_name)
        if not lyrics:
            await ctx.send("Lyrics not found.")
            return
        lines = [line.strip() for line in lyrics.splitlines() if line.strip()]
        if not lines:
            await ctx.send("No valid lyrics found.")
            return
        if lyric_task:
            lyric_task.cancel()
        async def update_status_loop():
            try:
                while True:
                    for line in lines:
                        await set_custom_status(bot.http.token, line)
                        await asyncio.sleep(1.5)
            except asyncio.CancelledError:
                await set_custom_status(bot.http.token, "")
        lyric_task = asyncio.create_task(update_status_loop())
        await ctx.send("Started lyrics status.")

    @bot.command()
    async def stoplyrics(ctx):
        await ctx.message.delete()
        nonlocal lyric_task
        if lyric_task:
            lyric_task.cancel()
            lyric_task = None
            await set_custom_status(bot.http.token, "")
            await ctx.send("Stopped lyrics status.")
        else:
            await ctx.send("No lyrics status running.")

    @bot.command()
    async def controlrpc(ctx, user: discord.User, activity_type: str, *, activity_message: str):
        await ctx.message.delete()
        if ctx.author.id not in watched_channel:
            return
        try:
            bot_user = next(b for b in all_bots if b.user.id == user.id)
        except StopIteration:
            await ctx.send("User not controlled by any bot.")
            return
        types = {
            "playing": discord.Game,
            "streaming": discord.Streaming,
            "listening": discord.Activity,
            "watching": discord.Activity,
            "competing": discord.Activity
        }
        activity_type = activity_type.lower()
        if activity_type == "streaming":
            activity = discord.Streaming(name=activity_message, url="https://twitch.tv/yourchannel")
        elif activity_type in types:
            if activity_type == "playing":
                activity = types[activity_type](name=activity_message)
            else:
                enum_type = getattr(discord.ActivityType, activity_type)
                activity = discord.Activity(type=enum_type, name=activity_message)
        else:
            await ctx.send("Invalid activity type.")
            return
        await bot_user.change_presence(activity=activity)

    @bot.command()
    async def controlsay(ctx, user: discord.User, *, message: str):
        await ctx.message.delete()
        if ctx.author.id not in watched_channel:
            return
        try:
            bot_user = next(b for b in all_bots if b.user.id == user.id)
        except StopIteration:
            await ctx.send("User not controlled by any bot.")
            return
        for channel in bot_user.private_channels:
            if isinstance(channel, discord.DMChannel):
                try:
                    await channel.send(message)
                except:
                    pass

    @bot.command()
    async def gclock(ctx, target: str, gc_id: int):
        await ctx.message.delete()
        if ctx.author.id not in watched_channel:
            await ctx.send("You are not authorized to use this command.")
            return
        channel = bot.get_channel(gc_id)
        if not channel or not hasattr(channel, "recipients"):
            await ctx.send("Invalid group DM channel ID.")
            return
        if target.lower() == "all":
            for member in getattr(channel, "recipients", []):
                if getattr(member, "bot", False):
                    continue
                locked_gcs.setdefault(member.id, set()).add(gc_id)
                try:
                    await channel.add_recipients(member)
                except Exception:
                    pass
            await ctx.send(f"Locked all non-bot users out of GC {gc_id}.")
        else:
            try:
                user = await commands.UserConverter().convert(ctx, target)
            except:
                await ctx.send("Invalid user.")
                return
            locked_gcs.setdefault(user.id, set()).add(gc_id)
            try:
                await channel.add_recipients(user)
            except Exception:
                pass
            await ctx.send(f"Locked {user.name} out of GC {gc_id}.")

    @bot.command()
    async def gcunlock(ctx, target: str, gc_id: int):
        await ctx.message.delete()
        if ctx.author.id not in watched_channel:
            await ctx.send("You are not authorized to use this command.")
            return
        channel = bot.get_channel(gc_id)
        if not channel or not hasattr(channel, "recipients"):
            await ctx.send("Invalid group DM channel ID.")
            return
        if target.lower() == "all":
            to_remove = []
            for user_id, gcs in locked_gcs.items():
                if gc_id in gcs:
                    gcs.remove(gc_id)
                if not gcs:
                    to_remove.append(user_id)
            for user_id in to_remove:
                locked_gcs.pop(user_id, None)
            await ctx.send(f"Unlocked all users in GC {gc_id}.")
        else:
            try:
                user = await commands.UserConverter().convert(ctx, target)
            except:
                await ctx.send("Invalid user.")
                return
            if user.id in locked_gcs and gc_id in locked_gcs[user.id]:
                locked_gcs[user.id].remove(gc_id)
                if not locked_gcs[user.id]:
                    locked_gcs.pop(user.id, None)
                await ctx.send(f"Unlocked {user.name} in GC {gc_id}.")
            else:
                await ctx.send(f"{user.name} was not locked in GC {gc_id}.")

    @bot.command()
    async def gcview(ctx, gc_id: int):
        await ctx.message.delete()
        if ctx.author.id not in watched_channel:
            return
        channel = bot.get_channel(gc_id)
        if not channel or not hasattr(channel, "recipients"):
            await ctx.send("Invalid group DM channel ID.")
            return
        locked_members = []
        for user_id, gcs in locked_gcs.items():
            if gc_id in gcs:
                user = bot.get_user(user_id)
                locked_members.append(user.name if user else str(user_id))
        if not locked_members:
            await ctx.send("No locked users in this group chat.")
        else:
            await ctx.send("Locked users:\n" + "\n".join(locked_members))

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
      
