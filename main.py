import discord
from discord.ext import tasks
from discord import app_commands
import socket
import struct
import json
import time
import os
 
# ============================================================
#   EDIT THESE 3 THINGS ONLY
# ============================================================
MINECRAFT_IP   = "play.shivxtreme.fun"   # e.g. "play.hypixel.net"
MINECRAFT_PORT = 19132               # default Minecraft port
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")   # paste your bot token here
# ============================================================
 
# Right-click your channel → Copy Channel ID (need Developer Mode on in Discord settings)
STATUS_CHANNEL_ID = 1565658810052  # <-- replace with your channel ID
 
 
def ping_minecraft(host, port, timeout=5):
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
 
        host_bytes = host.encode("utf-8")
        data = b""
        data += b"\x00"
        data += b"\x00"
        data += struct.pack(">B", len(host_bytes)) + host_bytes
        data += struct.pack(">H", port)
        data += b"\x01"
 
        sock.send(struct.pack(">B", len(data)) + data)
        sock.send(b"\x01\x00")
 
        def read_varint(s):
            result, shift = 0, 0
            while True:
                byte = s.recv(1)
                if not byte:
                    return 0
                b = byte[0]
                result |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    return result
 
        read_varint(sock)
        read_varint(sock)
        str_len = read_varint(sock)
 
        raw = b""
        while len(raw) < str_len:
            chunk = sock.recv(str_len - len(raw))
            if not chunk:
                break
            raw += chunk
 
        sock.close()
 
        info = json.loads(raw.decode("utf-8"))
        players_online = info.get("players", {}).get("online", 0)
        players_max    = info.get("players", {}).get("max", 0)
        player_list    = [p.get("name", "Unknown") for p in info.get("players", {}).get("sample", [])]
        motd = info.get("description", {})
        if isinstance(motd, dict):
            motd = motd.get("text", "")
        elif not isinstance(motd, str):
            motd = str(motd)
 
        return {
            "online": True,
            "players_online": players_online,
            "players_max": players_max,
            "player_list": player_list,
            "motd": motd,
        }
 
    except Exception:
        return {"online": False}
 
 
def build_embed(info):
    if not info["online"]:
        embed = discord.Embed(
            title="🔴  Minecraft Server — OFFLINE",
            description=f"`{MINECRAFT_IP}:{MINECRAFT_PORT}`",
            color=discord.Color.red(),
        )
        embed.set_footer(text=f"Last checked: {time.strftime('%H:%M:%S')}")
        return embed
 
    players = info["players_online"]
    max_p   = info["players_max"]
    names   = info["player_list"]
 
    embed = discord.Embed(
        title="🟢  Minecraft Server — ONLINE",
        description=f"`{MINECRAFT_IP}:{MINECRAFT_PORT}`",
        color=discord.Color.green(),
    )
    embed.add_field(name="👥 Players", value=f"**{players} / {max_p}**", inline=True)
 
    if names:
        embed.add_field(name="🧍 Online Now", value="\n".join(f"• {n}" for n in names), inline=True)
    elif players > 0:
        embed.add_field(name="🧍 Online Now", value=f"{players} player(s) (names hidden by server)", inline=True)
    else:
        embed.add_field(name="🧍 Online Now", value="Nobody online yet", inline=True)
 
    if info["motd"]:
        embed.add_field(name="📋 MOTD", value=info["motd"], inline=False)
 
    embed.set_footer(text=f"Updates every 30 sec • Last checked: {time.strftime('%H:%M:%S')}")
    return embed
 
 
# ─── Bot Setup ────────────────────────────────────────────────
 
intents = discord.Intents.default()
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)
 
status_message = None
 
# Render pe /tmp temporary hai lekin restart ke beech kaam karta hai
MESSAGE_ID_FILE = "/tmp/status_message_id.txt"
 
 
def save_message_id(msg_id: int):
    """Message ID ko file me save karo taaki restart ke baad bhi mile"""
    with open(MESSAGE_ID_FILE, "w") as f:
        f.write(str(msg_id))
 
 
def load_message_id():
    """File se pehle wala message ID load karo"""
    try:
        with open(MESSAGE_ID_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None
 
 
# ─── /status slash command ────────────────────────────────────
 
@tree.command(name="status", description="Check the Minecraft server status right now")
async def status_command(interaction: discord.Interaction):
    await interaction.response.defer()
    info  = ping_minecraft(MINECRAFT_IP, MINECRAFT_PORT)
    embed = build_embed(info)
    await interaction.followup.send(embed=embed)
 
 
# ─── Auto updater (every 30 sec) ──────────────────────────────
 
@tasks.loop(seconds=30)
async def update_status():
    global status_message
 
    channel = client.get_channel(STATUS_CHANNEL_ID)
    if channel is None:
        print(f"❌ Could not find channel ID {STATUS_CHANNEL_ID}")
        return
 
    info  = ping_minecraft(MINECRAFT_IP, MINECRAFT_PORT)
    embed = build_embed(info)
 
    try:
        # Memory me nahi hai? File se ID load karke Discord se fetch karo
        if status_message is None:
            saved_id = load_message_id()
            if saved_id:
                try:
                    status_message = await channel.fetch_message(saved_id)
                    print(f"✅ Purana message mil gaya (ID: {saved_id}), ab edit hoga")
                except discord.NotFound:
                    print("⚠️ Purana message delete ho chuka tha, naya bana raha hu...")
                    status_message = None
 
        if status_message is None:
            # Pehli baar ya message delete ho gaya — sirf tab naya bhejo
            status_message = await channel.send(embed=embed)
            save_message_id(status_message.id)
            print(f"📨 Naya status message bheja (ID: {status_message.id})")
        else:
            # Bas edit karo — koi naya message nahi
            await status_message.edit(embed=embed)
 
    except discord.NotFound:
        # Message manually delete ho gaya beech me
        status_message = await channel.send(embed=embed)
        save_message_id(status_message.id)
        print(f"📨 Message delete tha, naya bheja (ID: {status_message.id})")
    except Exception as e:
        print(f"❌ Update error: {e}")
 
    state = "ONLINE" if info["online"] else "OFFLINE"
    print(f"[{time.strftime('%H:%M:%S')}] Server is {state} — {info.get('players_online', 0)} players")
 
 
@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user}")
    print(f"   Monitoring: {MINECRAFT_IP}:{MINECRAFT_PORT}")
    print(f"   Slash command /status is ready!")
    update_status.start()
 
 
client.run(DISCORD_TOKEN)
 
