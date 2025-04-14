import json
import os
import io
import contextlib
import requests
import openai
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from PIL import Image
from flask import Flask

API_ID = 20167916
API_HASH = "325de70c258003ff1c30fb02077dde25"
BOT_TOKEN = "8173268123:AAGAKuPh7up7VyQ0VBFgwqRnbIcIC6lbd54"
OWNER_ID = 6672752177
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

openai.api_key = OPENAI_API_KEY
ADMINS_FILE = "admins.json"

if not os.path.exists(ADMINS_FILE):
    with open(ADMINS_FILE, "w") as f:
        json.dump([OWNER_ID], f)

def load_admins():
    with open(ADMINS_FILE) as f:
        return json.load(f)

def save_admins(admins):
    with open(ADMINS_FILE, "w") as f:
        json.dump(admins, f)

def is_admin_user(uid):
    return uid in load_admins()

def is_admin():
    return filters.create(lambda _, __, m: is_admin_user(m.from_user.id))

async def add_admin(uid: int):
    admins = load_admins()
    if uid not in admins:
        admins.append(uid)
        save_admins(admins)

async def remove_admin(uid: int):
    admins = load_admins()
    if uid in admins and uid != OWNER_ID:
        admins.remove(uid)
        save_admins(admins)

app = Client("SuhoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply("I'm alive. Use /help to see commands.")

@app.on_message(filters.command("help"))
async def help_cmd(client, message: Message):
    await message.reply(
        "**Available Commands:**\n"
        "/eval <code> - Run Python code\n"
        "/addadmin - Add admin (reply or ID)\n"
        "/removeadmin - Remove admin\n"
        "/admins - List admins\n"
        "/suho <prompt> - AI chat via OpenRouter\n"
        "/openai <prompt> - AI chat via OpenAI\n"
        "/openaiimg <prompt> - Generate image via OpenAI\n"
        "/upscale - Reply to image to upscale"
    )

@app.on_message(filters.command("eval") & is_admin())
async def eval_cmd(client, message: Message):
    code = message.text.split(None, 1)
    if len(code) < 2:
        return await message.reply("Give me some code to run.")
    code = code[1]
    local_vars = {}
    stdout = io.StringIO()
    try:
        exec(
            "async def __eval_fn(client, message):\n" +
            "\n".join(f"    {line}" for line in code.split("\n")),
            globals(),
            local_vars
        )
        with contextlib.redirect_stdout(stdout):
            result = await local_vars["__eval_fn"](client, message)
        output = stdout.getvalue()
        if result is not None:
            output += str(result)
        if not output.strip():
            output = "✅ Code executed successfully. (no output)"
        await message.reply(f"**Output:**\n```\n{output.strip()}\n```")
    except Exception as e:
        await message.reply(f"**Error:** `{e}`")

@app.on_message(filters.command("addadmin") & filters.user(OWNER_ID))
async def add_admin_cmd(client, message: Message):
    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(arg)
        except:
            return await message.reply("User not found.")
    if not target:
        return await message.reply("Reply or provide ID/@username.")
    if is_admin_user(target.id):
        return await message.reply("User is already an admin.")
    await add_admin(target.id)
    await message.reply(f"✅ `{target.first_name}` added as admin.")

@app.on_message(filters.command("removeadmin") & filters.user(OWNER_ID))
async def remove_admin_cmd(client, message: Message):
    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(arg)
        except:
            return await message.reply("User not found.")
    if not target:
        return await message.reply("Reply or provide ID/@username.")
    if target.id == OWNER_ID:
        return await message.reply("Can't remove owner.")
    if not is_admin_user(target.id):
        return await message.reply("User is not an admin.")
    await remove_admin(target.id)
    await message.reply(f"❌ `{target.first_name}` removed from admin list.")

@app.on_message(filters.command("admins") & is_admin())
async def list_admins_cmd(client, message: Message):
    text = f"**👑 Owner:** [{OWNER_ID}](tg://user?id={OWNER_ID})\n\n**🛡️ Admins:**\n"
    has_admins = False
    for uid in load_admins():
        if uid == OWNER_ID:
            continue
        has_admins = True
        try:
            user = await client.get_users(uid)
            text += f"• [{user.first_name}](tg://user?id={uid}) (`{uid}`)\n"
        except:
            text += f"• `{uid}` (User not found)\n"
    if not has_admins:
        text += "_No other admins added yet._"
    await message.reply(text)

@app.on_message(filters.command("suho") & is_admin())
async def suho_openrouter(client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Send something like: `/suho tell me a joke`")

    prompt = message.text.split(None, 1)[1]
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "mistralai/mistral-7b-instruct:free",
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        r.raise_for_status()
        reply = r.json()["choices"][0]["message"]["content"]
        await message.reply(reply)
    except Exception as e:
        await message.reply(f"**Suho error:** `{e}`")
        
@app.on_message(filters.command("upscale") & is_admin())
async def upscale_choose(client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        return await message.reply("Reply to a photo with `/upscale` to choose scale.")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{factor}×", callback_data=f"upscale_{factor}")]
        for factor in [2, 4, 6, 8, 10, 16]
    ])

    await message.reply("Choose upscale factor:", reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"upscale_(\d+)"))
async def handle_upscale_callback(client, callback: CallbackQuery):
    if not callback.message.reply_to_message or not callback.message.reply_to_message.photo:
        return await callback.answer("Photo not found.", show_alert=True)

    factor = int(callback.data.split("_")[1])
    await callback.answer(f"Upscaling {factor}×...", show_alert=False)

    try:
        photo = await callback.message.reply_to_message.download()
        img = Image.open(photo)

        width, height = img.size
        upscaled = img.resize((width * factor, height * factor), Image.LANCZOS)

        output_path = f"upscaled_{factor}x.png"
        upscaled.save(output_path)

        await client.send_document(
            chat_id=callback.from_user.id,
            document=output_path,
            caption=f"Here’s your {factor}× upscaled image."
        )

        await callback.message.reply_document(
            output_path,
            caption=f"Upscaled to {factor}× successfully!"
        )

        os.remove(output_path)
        os.remove(photo)

    except Exception as e:
        await callback.message.reply(f"**Upscale error:** `{e}`")

# --- Flask app for Render health check ---
web = Flask(__name__)

@web.route('/')
def home():
    return "Bot is running!"


from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

@app.on_message(filters.command("upscale") & is_admin())
async def upscale_choose(client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        return await message.reply("Reply to a photo with `/upscale` to choose scale.")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("2×", callback_data="upscale_2"),
         InlineKeyboardButton("4×", callback_data="upscale_4")],
        [InlineKeyboardButton("6×", callback_data="upscale_6"),
         InlineKeyboardButton("8×", callback_data="upscale_8")],
        [InlineKeyboardButton("10×", callback_data="upscale_10")]
    ])

    await message.reply("Choose upscale factor:", reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"upscale_\d+"))
async def handle_upscale_callback(client, callback: CallbackQuery):
    if not callback.message.reply_to_message or not callback.message.reply_to_message.photo:
        return await callback.answer("Photo not found.", show_alert=True)

    factor = int(callback.data.split("_")[1])
    await callback.answer(f"Upscaling {factor}×...", show_alert=False)

    try:
        photo = await callback.message.reply_to_message.download()
        img = Image.open(photo)

        width, height = img.size
        upscaled = img.resize((width * factor, height * factor), Image.LANCZOS)

        output_path = f"upscaled_{factor}x.png"
        upscaled.save(output_path)

        await callback.message.reply_photo(output_path, caption=f"Here’s your {factor}× upscaled image.")
        os.remove(output_path)
        os.remove(photo)
    except Exception as e:
        await callback.message.reply(f"**Upscale error:** `{e}`")

import threading

def run_web():
    web.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

def run_bot():
    import time
    while True:
        try:
            app.run()
        except Exception as e:
            print(f"Bot crashed with error: {e}. Restarting in 5 seconds...")
            time.sleep(5)

threading.Thread(target=run_web).start()
run_bot()

# --- AFK THOUGHT LOADING ---
import time

def load_thoughts(file_path):
    try:
        with open(file_path, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return ["No thoughts available."]

thoughts_18_plus = load_thoughts("thoughts/thoughts_18.txt")
thoughts_under_18 = load_thoughts("thoughts/thoughts_u18.txt")

afk_users = {}

@app.on_message(filters.command("afk"))
async def set_afk(client, message: Message):
    user = message.from_user
    reason = " ".join(message.command[1:]) if len(message.command) > 1 else "No reason provided."
    afk_users[user.id] = {"start": time.time(), "reason": reason}
    await message.reply(f"{user.mention} is now AFK.")

@app.on_message(filters.private | filters.group)
async def check_afk(client, message: Message):
    if message.from_user and message.from_user.id in afk_users:
        start_time = afk_users[message.from_user.id]["start"]
        elapsed = int(time.time() - start_time)
        reason = afk_users[message.from_user.id]["reason"]

        # Pick random thought
        import random
        if random.randint(1, 100) <= 75:
            thought = random.choice(thoughts_18_plus)
        else:
            thought = random.choice(thoughts_under_18)

        if elapsed < 60:
            time_str = f"{elapsed} seconds"
        else:
            time_str = f"{elapsed // 60} minutes {elapsed % 60} seconds"

        msg = (
            f"{message.from_user.first_name} "
        
"
            f"**Thought**: {thought}"
            f"\n**𝖠𝖥𝖪 𝖿𝗈𝗋**: {time_str}"
            f"\n**𝖱𝖾𝖺𝗌𝗈𝗇**: {reason}"
        )
        await message.reply_text(msg)
# --- AFK SYSTEM END ---
