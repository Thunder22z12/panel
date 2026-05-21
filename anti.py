import discord
from discord.ext import commands
import re
from collections import deque
from groq import Groq
import asyncio
import os

# ========== CONFIGURATION ==========
USER_TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = "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"

MAX_HISTORY = 10

EXTRACT_PROMPT = """You are a bot that extracts the secret answer from a Discord message used for AFK checks. Extract the secret answer from the message. Return ONLY the exact word/phrase, nothing else – no explanation, no extra words, no punctuation. If the message does NOT contain any request for a specific answer, return just: NONE
Examples:
- "afk check say pineapple" → pineapple
- "kw = strawberry" → strawberry
- "reply with hello" → hello
- "type: apple" → apple
- "||hidden|| answer is watermelon" → watermelon
- "**bold** keyword: orange" → orange
- "verify: cat" → cat
- "what is the secret word? banana" → banana
- "what is capital of russia? → moscow
- "what is date today?" → 26 jan
- "tell what is formula of Sodium Chloride" → NaCl
- "what is fastest animal?" → cheetah
- "what is 1+1*1/1+1?" → 1
Return ONLY the answer word/phrase, nothing else."""

client = Groq(api_key=GROQ_API_KEY)

# Original strict counting regexes (require at least two items)
NUMBERS_PATTERN = re.compile(r'^(\d+\s+)+\d+$')
ROMAN_PATTERN = re.compile(r'^([IVXLCDMivxlcdm]+\s+)+[IVXLCDMivxlcdm]+$')
WORD_NUM_PATTERN = re.compile(r'^([A-Za-z]+\d+\s+)+[A-Za-z]+\d+$')
ENGLISH_NUMBERS = r'(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)'
ENGLISH_PATTERN = re.compile(r'^(' + ENGLISH_NUMBERS + r'\s+)+' + ENGLISH_NUMBERS + r'$', re.IGNORECASE)

def roman_to_int(roman: str) -> int | None:
    roman = roman.upper().strip()
    values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    total = 0
    prev = 0
    for ch in reversed(roman):
        val = values.get(ch)
        if val is None:
            return None
        if val < prev:
            total -= val
        else:
            total += val
        prev = val
    return total if total <= 20 else None  # limit to 20 for AFK checks

def word_to_int(word: str) -> int | None:
    word = word.lower().strip()
    words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
        "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
        "nineteen": 19, "twenty": 20
    }
    return words.get(word)

def parse_count_number(text: str) -> int | None:
    text = text.strip()
    if text.isdigit():
        return int(text)
    roman_val = roman_to_int(text)
    if roman_val is not None:
        return roman_val
    return word_to_int(text)

def is_counting_message(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    return (bool(NUMBERS_PATTERN.match(text)) or
                bool(ROMAN_PATTERN.match(text)) or
                bool(WORD_NUM_PATTERN.match(text)) or
                bool(ENGLISH_PATTERN.match(text)))

def simple_keyword_extract(text: str) -> str | None:
    """Fallback extraction if Groq fails."""
    patterns = [
        r'kw\s*=\s*(\w+)',
        r'say\s+(\w+)',
        r'reply with\s+(\w+)',
        r'type:\s*(\w+)',
        r'answer is\s+(\w+)',
        r'keyword:?\s*(\w+)'
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def extract_answer_from_message(message_text: str) -> str | None:
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": message_text}
            ],
            temperature=0.0,
            max_tokens=50
        )
        answer = response.choices[0].message.content.strip()
        if answer == "NONE" or not answer:
            return simple_keyword_extract(message_text)
        return answer
    except Exception as e:
        print(f"[Groq Error] {e}")
        return simple_keyword_extract(message_text)

# ========== DISCORD SELF‑BOT ==========
bot = commands.Bot(command_prefix=".", self_bot=True, help_command=None)
target_channel_id = None
user_last_number = {}
user_history = {}
# Track whether we have already replied to the last known instruction for each user
replied_for_instruction = {}

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print("⚠️ Use .anti <channel_id> to start monitoring")

@bot.command(name="anti")
async def set_anti(ctx, channel_id: int):
    global target_channel_id
    target_channel_id = channel_id
    await ctx.send(f"Monitoring AFK checks in <#{channel_id}>")
    print(f"Monitoring channel {channel_id}")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("Pong!")

@bot.event
async def on_message(message):
    global target_channel_id

    await bot.process_commands(message)

    if message.author == bot.user:
        return
    if target_channel_id is None:
        return
    if message.channel.id != target_channel_id:
        return

    author_id = message.author.id
    content = message.content

    # Update history (store both content and message object)
    if author_id not in user_history:
        user_history[author_id] = deque(maxlen=MAX_HISTORY)
    user_history[author_id].append((content, message))

    num = parse_count_number(content)
    if num is not None:
        # Get the last number this user sent (default 0)
        last_num = user_last_number.get(author_id, 0)
        if num == last_num + 1:
            # It's the next number in sequence
            user_last_number[author_id] = num
            
            # After reaching 3 (or any target), trigger reply
            if num == 9:
                # Find the latest instruction from history
                history = list(user_history.get(author_id, []))
                answer = None
                for prev_content, _ in reversed(history):
                    if prev_content == content:  # skip current
                        continue
                    extracted = extract_answer_from_message(prev_content)
                    if extracted:
                        answer = extracted
                        break
                if answer:
                    await message.channel.send(f"# {answer}")
                    print(f"   -> Replied with: {answer}")
                # Reset the counter for this user so it doesn't reply again
                user_last_number[author_id] = 0
        else:
            # Not a consecutive number – reset counter
            user_last_number[author_id] = 0
    else:
        # Non‑numeric message: could be a new instruction
        keys_to_delete = [k for k in replied_for_instruction if k[0] == author_id]
        for k in keys_to_delete:
            del replied_for_instruction[k]
        user_last_number[author_id] = 0

if __name__ == "__main__":
    if USER_TOKEN.startswith("YOUR_"):
        print(" replace USER_TOKEN with a valid token")
    else:
        bot.run(USER_TOKEN)
