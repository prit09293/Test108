import os
import io
import re
import time
import contextlib
import requests
import threading
from flask import Flask
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import whisper
from pymongo import MongoClient

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
MONGO_URI = os.environ.get("MONGO_URI")
OWNER_ID = 6672752177

mongo = MongoClient(MONGO_URI)
db = mongo["suho_bot"]
admins_col = db["admins"]
afk_col = db["afk"]
modes_col = db["search_modes"]

app = Client("SuhoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def is_admin_user(uid):
    return admins_col.find_one({"_id": uid}) is not None

def is_admin():
    return filters.create(lambda _, __, m: is_admin_user(m.from_user.id))

def set_afk(uid, reason=""):
    afk_col.replace_one({"_id": uid}, {"_id": uid, "reason": reason, "time": time.time()}, upsert=True)

def get_afk(uid):
    return afk_col.find_one({"_id": uid})

def clear_afk(uid):
    afk_col.delete_one({"_id": uid})

def set_mode(uid, mode):
    modes_col.replace_one({"_id": uid}, {"_id": uid, "mode": mode}, upsert=True)

def get_mode(uid):
    data = modes_col.find_one({"_id": uid})
    return data["mode"] if data else "telegram"

@app.on_message(filters.command("addadmin") & filters.user(OWNER_ID))
async def add_admin(client, message):
    if len(message.command) < 2:
        return await message.reply("Use: /addadmin <user_id>")
    try:
        uid = int(message.command[1])
        if not is_admin_user(uid):
            admins_col.insert_one({"_id": uid})
        await message.reply(f"Added admin: {uid}")
    except:
        await message.reply("Invalid ID")

@app.on_message(filters.command("admins") & is_admin())
async def list_admins(client, message):
    all_ids = admins_col.find()
    ids = [str(doc["_id"]) for doc in all_ids]
    await message.reply("Admins:
" + "
".join(ids))

@app.on_message(filters.command("afk"))
async def afk_cmd(client, message: Message):
    reason = message.text.split(None, 1)[1] if len(message.command) > 1 else ""
    set_afk(message.from_user.id, reason)
    await message.reply("AFK set." + (f"
Reason: {reason}" if reason else ""))

@app.on_message(filters.group & ~filters.service)
async def return_afk(client, message: Message):
    uid = message.from_user.id
    afk = get_afk(uid)
    if afk:
        minutes = int((time.time() - afk["time"]) / 60)
        clear_afk(uid)
        await message.reply(f"Welcome back! You were AFK for {minutes} minute(s).")

@app.on_message(filters.command("searchmode"))
async def search_mode_cmd(client, message: Message):
    if len(message.command) < 2 or message.command[1] not in ["telegram", "instant"]:
        return await message.reply("Usage: /searchmode telegram|instant")
    set_mode(message.from_user.id, message.command[1])
    await message.reply(f"Mode set to: {message.command[1]}")

@app.on_message(filters.command("search"))
async def search_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Use: /search <query>")
    query = message.text.split(None, 1)[1]
    mode = get_mode(message.from_user.id)
    try:
        url = f"https://nyaa.si/?f=0&c=0_0&q={query}&s=seeders&o=desc"
        r = requests.get(url)
        entries = re.findall(r'<tr.*?class="(?:default|danger|success)".*?</tr>', r.text, re.S)
        results = []
        for entry in entries[:5]:
            try:
                title = re.search(r'title="([^"]+)"', entry).group(1)
                link = "https://nyaa.si" + re.search(r'href="(/view/\d+)"', entry).group(1)
                magnet = re.search(r'href="(magnet:\?xt=urn:btih:[^"]+)"', entry).group(1)
                size = re.search(r'<td class="text-center">([^<]+)</td>', entry).group(1)
                seeders = re.findall(r'<td class="text-center">(\d+)</td>', entry)[-2]
                results.append((title, link, magnet, size, seeders))
            except: continue

        for title, link, magnet, size, seeders in results:
            await message.reply(f"**{title}**\nSize: {size} | Seeders: {seeders}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Magnet", url=magnet)],
                    [InlineKeyboardButton("Nyaa", url=link)]
                ]))
    except Exception as e:
        await message.reply(f"Error: {e}")

@app.on_message(filters.command("suho"))
async def suho_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Use: /suho <prompt>")
    prompt = message.text.split(None, 1)[1]
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "mistralai/mistral-7b-instruct:free",
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        result = r.json()["choices"][0]["message"]["content"]
        await message.reply(result)
    except Exception as e:
        await message.reply(f"Error: {e}")

@app.on_message(filters.command("voice"))
async def voice_cmd(client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.voice:
        return await message.reply("Reply to a voice message.")
    try:
        vfile = await message.reply_to_message.download()
        model = whisper.load_model("base")
        result = model.transcribe(vfile)
        await message.reply(result["text"])
        os.remove(vfile)
    except Exception as e:
        await message.reply(f"Voice error: {e}")

@app.on_message(filters.command("upscale"))
async def upscale_cmd(client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        return await message.reply("Reply to an image with /upscale 2x–10x")
    try:
        factor = int(message.command[1].replace("x", ""))
        if factor < 2 or factor > 10:
            return await message.reply("Use /upscale 2x to 10x only.")
        photo = await message.reply_to_message.download()
        img = Image.open(photo)
        size = (img.width * factor, img.height * factor)
        upscaled = img.resize(size, Image.LANCZOS)
        upscaled.save("upscaled.png")
        await message.reply_photo("upscaled.png", caption=f"{factor}× upscaled!")
        os.remove("upscaled.png")
        os.remove(photo)
    except Exception as e:
        await message.reply(f"Upscale error: {e}")

@app.on_message(filters.command("eval") & is_admin())
async def eval_cmd(client, message: Message):
    code = message.text.split(None, 1)
    if len(code) < 2:
        return await message.reply("Give me some code.")
    code = code[1]
    local_vars = {}
    stdout = io.StringIO()
    try:
        exec("async def __eval_fn(client, message):\n" +
             "\n".join(f"    {line}" for line in code.split("\n")),
             globals(), local_vars)
        with contextlib.redirect_stdout(stdout):
            result = await local_vars["__eval_fn"](client, message)
        output = stdout.getvalue()
        if result is not None:
            output += str(result)
        await message.reply(f"**Output:**\n```\n{output.strip()}\n```")
    except Exception as e:
        await message.reply(f"**Error:** `{e}`")

# === Flask + Bot Run ===
web = Flask(__name__)

@web.route("/")
def home():
    return "Bot is alive!"

def run_web():
    web.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

def run_bot():
    app.run()

threading.Thread(target=run_web).start()
run_bot()