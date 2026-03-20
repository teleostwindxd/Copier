import discord
from discord.ext import commands
import json
import os
import asyncio
from flask import Flask
from threading import Thread

# --- RENDER WEB SERVER (Keep-Alive) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is online and cloning at maximum speed!"

def run_server():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_server)
    t.start()

# --- DISCORD BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "server_messages.json"

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
@commands.has_permissions(administrator=True)
async def copy(ctx):
    await ctx.send("Starting the cloning process. Fetching all messages...")
    all_messages = []
    
    for channel in ctx.guild.text_channels:
        channel_messages = []
        try:
            # oldest_first=True ensures correct chronological pasting
            async for msg in channel.history(limit=None, oldest_first=True):
                if not msg.content:
                    continue # Skips pure attachments/images/videos
                
                channel_messages.append({
                    "channel": channel.name,
                    "author_id": str(msg.author.id),
                    "author_name": msg.author.display_name,
                    "author_avatar": msg.author.display_avatar.url if msg.author.display_avatar else None,
                    "content": msg.content,
                    "date_str": msg.created_at.strftime("%m/%d/%Y , %I:%M %p"),
                    "use_webhook": False
                })
            all_messages.extend(channel_messages)
            print(f"Fetched #{channel.name}")
        except Exception as e:
            print(f"Skipped #{channel.name} due to error: {e}")

    # Flag the absolute latest 25 messages per user globally for Webhooks
    user_counts = {}
    for msg in reversed(all_messages):
        uid = msg["author_id"]
        if user_counts.get(uid, 0) < 25:
            msg["use_webhook"] = True
            user_counts[uid] = user_counts.get(uid, 0) + 1

    # Group by channel so we can paste channel-by-channel
    server_data = {}
    for msg in all_messages:
        c = msg["channel"]
        if c not in server_data:
            server_data[c] = []
        server_data[c].append(msg)

    # Save to Render's temporary disk
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(server_data, f, indent=4)
        
    await ctx.send("Copy complete! Data saved. Run `!paste` in the new server immediately.")

@bot.command()
@commands.has_permissions(administrator=True)
async def paste(ctx):
    await ctx.send("Pasting messages at absolute maximum speed...")
    
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            server_data = json.load(f)
    except FileNotFoundError:
        return await ctx.send("No copied data found. Run `!copy` first.")

    for channel in ctx.guild.text_channels:
        if channel.name in server_data and server_data[channel.name]:
            print(f"Pasting in #{channel.name}")
            webhook = await channel.create_webhook(name="MessageCloner")
            
            for msg in server_data[channel.name]:
                try:
                    if msg["use_webhook"]:
                        # Webhook format for the latest 25 per user
                        await webhook.send(
                            content=msg["content"],
                            username=msg["author_name"],
                            avatar_url=msg["author_avatar"]
                        )
                    else:
                        # Standard format for older messages to save time
                        formatted_text = f"**{msg['author_name']}** ({msg['date_str']}) : {msg['content']}"
                        await channel.send(formatted_text)
                        
                except discord.errors.HTTPException as e:
                    # discord.py usually auto-handles rate limits, but this catches hard blocks
                    print(f"Hit API limit in #{channel.name}: {e}. Pausing for 3 seconds...")
                    await asyncio.sleep(3) 
                except Exception as e:
                    print(f"Failed message in #{channel.name}: {e}")
            
            await webhook.delete()
            
    await ctx.send("Server perfectly cloned!")

# 1. Start the Flask keep-alive server in the background
keep_alive()

# 2. Boot the Discord bot on the main thread
bot.run(os.environ.get('DISCORD_TOKEN'))
                  
