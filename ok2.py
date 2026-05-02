import discord
import asyncio
import random
import os

TOKEN = os.getenv("TOKEN")

client = discord.Client(self_bot=True)

tasks = {}  # channel_id -> task
fake_typing = False
typing_task = None
status_task = None
name_task = None
spam_task = None
afk_task = None

statuses=["#1"]

def load_lines(file_name):
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    except Exception as e:
        print("Load error:", e)
        return []


async def scheduler(channel, delay, file_name):
    while True:
        lines = load_lines(file_name)

        if not lines:
            await asyncio.sleep(5)
            continue

        random.shuffle(lines)

        for line in lines:
            try:
                await channel.send(line)
                await asyncio.sleep(delay)
            except Exception as e:
                print("Send error:", e)
                await asyncio.sleep(5)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
    global fake_typing, typing_task, status_task, name_task, spam_task, afk_task
    if message.author != client.user:
        return

    content = message.content.split()

    # .schedule <channel_id> <delay> <file>
    if len(content) == 4 and content[0] == ".schedule":
        try:
            channel_id = int(content[1])
            delay = float(content[2])
            file_name = content[3]

            channel = client.get_channel(channel_id)
            if not channel:
                await message.channel.send("Invalid channel ID")
                return

            # stop old task if exists
            if channel_id in tasks:
                tasks[channel_id].cancel()

            task = client.loop.create_task(
                scheduler(channel, delay, file_name)
            )
            tasks[channel_id] = task

            await message.channel.send(
                f"Started scheduler in {channel_id} every {delay}s using {file_name}"
            )

        except:
            await message.channel.send("Usage: .schedule <channel_id> <delay> <file.txt>")

    # stop command
    if content[0] == ".stop":
        if len(content) == 2:
            channel_id = int(content[1])
            if channel_id in tasks:
                tasks[channel_id].cancel()
                del tasks[channel_id]
                await message.channel.send(f"Stopped {channel_id}")
        else:
            await message.channel.send("Usage: .stop <channel_id>")


        if content == ".schedule":
            fake_typing = True

            async def typing_loop():
                while fake_typing:
                    try:
                        await message.channel.trigger_typing()
                        await asyncio.sleep(5)  # typing interval
                    except:
                        break

        if typing_task:
            typing_task.cancel()

        typing_task = client.loop.create_task(typing_loop())
        await message.channel.send("st")

    # start cycling
    if message.content.startswith(".startnames"):
        names = message.content[12:].split(",")

        async def cycle_names():
            count = 0
            while count < 5000:
                for name in names:
                    try:
                        await message.channel.edit(name=name.strip())
                        print(f"Changed to: {name}")
                        await asyncio.sleep(1)  # SAFE DELAY
                        count += 1
                        if count >= 500000:
                            break
                    except Exception as e:
                        print("Error:", e)
                        await asyncio.sleep(60)

        name_task = client.loop.create_task(cycle_names())
        await message.channel.send("Started name cycling")
    
    if message.content == ".stopnames":
        if name_task:
            name_task.cancel()
            name_task = None
            await message.channel.send("Stopped name cycling")

    if content == ".status on":
        global status_task

        if status_task:
            status_task.cancel()

        async def status_loop():
            while True:
                for s in statuses:
                    await client.change_presence(
    activity=discord.Streaming(
        name=s,
        url="https://twitch.tv/yourchannel"
    )
)
                    await asyncio.sleep(10000000000000)

        status_task = client.loop.create_task(status_loop())
        await message.channel.send("Auto status ON")

    if content == ".status off":
        if status_task:
            status_task.cancel()
            await message.channel.send("Auto status OFF")

    # START SPAM
    if message.content.startswith(".spam"):
        spam_msg = message.content[6:]

        async def spam():
            while True:
                try:
                    await message.channel.send(spam_msg)
                    await asyncio.sleep(2)  # delay (change if you want)
                except Exception as e:
                    print("Error:", e)
                    await asyncio.sleep(10)

        spam_task = client.loop.create_task(spam())
        await message.channel.send("Spamming started")

    # STOP SPAM
    if message.content == ".stopspam":
        if spam_task:
            spam_task.cancel()
            spam_task = None
            await message.channel.send("Spamming stopped")

    # START AFK CHECK
    if message.content.startswith(".check"):
        parts = message.content.split()

        if len(parts) < 3 or len(message.mentions) != 1:
            await message.channel.send("Use: .afkcheck @user number")
            return

        user = message.mentions[0]

        try:
            limit = int(parts[-1])
        except:
            await message.channel.send("Enter a valid number")
            return

        # stop previous if running
        if afk_task:
            afk_task.cancel()

        async def afk_loop():
            for i in range(1, limit + 1):
                try:
                    await message.channel.send(f"{user.mention} {i}")
                    await asyncio.sleep(2)  # delay (important)
                except Exception as e:
                    print("AFK error:", e)
                    await asyncio.sleep(5)

        afk_task = client.loop.create_task(afk_loop())
        await message.channel.send(f" check started for {user}")

    # STOP AFK CHECK
    if message.content == ".stopafk":
        if afk_task:
            afk_task.cancel()
            afk_task = None
            await message.channel.send("AFK check stopped")

client.run(TOKEN)
