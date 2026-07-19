import discord
from discord.ext import tasks
from discord import app_commands
import socket
import struct
import json
import time
import os
import re
import asyncio
import random

# ============================================================
#   EDIT THESE
# ============================================================
MINECRAFT_IP      = "play.shivxtreme.fun"
MINECRAFT_PORT    = 25565
DISCORD_TOKEN     = os.environ.get("DISCORD_TOKEN")
STATUS_CHANNEL_ID = 1439258136278995026
# ============================================================

MESSAGE_ID_FILE = "/tmp/status_message_id.txt"

# Status toggle — sirf yeh users use kar sakte hain
status_enabled = True
STATUS_CONTROL_USERS = [955503311182790726, 919913690252320778]


def save_message_id(msg_id):
    with open(MESSAGE_ID_FILE, "w") as f:
        f.write(str(msg_id))


def load_message_id():
    try:
        with open(MESSAGE_ID_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def clean_motd(text):
    return re.sub(r'§.', '', str(text)).strip()


def get_java_player_names(host, port, timeout=3):
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        host_bytes = host.encode("utf-8")
        data = b"\x00\x00" + struct.pack(">B", len(host_bytes)) + host_bytes + struct.pack(">H", port) + b"\x01"
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
        return [p.get("name", "Unknown") for p in info.get("players", {}).get("sample", [])]
    except Exception:
        return []


def ping_minecraft(host, port, timeout=5):
    try:
        UNCONNECTED_PING = (
            b'\x01'
            + struct.pack('>q', int(time.time() * 1000))
            + b'\x00\xff\xff\x00\xfe\xfe\xfe\xfe\xfd\xfd\xfd\xfd\x12\x34\x56\x78'
            + struct.pack('>q', 2)
        )
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(UNCONNECTED_PING, (host, port))
        data, _ = sock.recvfrom(4096)
        sock.close()

        offset         = 1 + 8 + 8 + 16 + 2
        raw_str        = data[offset:].decode("utf-8", errors="ignore")
        parts          = raw_str.split(";")
        motd           = clean_motd(parts[1]) if len(parts) > 1 else ""
        sub_motd       = clean_motd(parts[7]) if len(parts) > 7 else ""
        players_online = int(parts[4]) if len(parts) > 4 else 0
        players_max    = int(parts[5]) if len(parts) > 5 else 0
        full_motd      = f"{motd} | {sub_motd}" if sub_motd else motd
        java_players   = get_java_player_names(host, port)

        return {
            "online": True,
            "players_online": players_online,
            "players_max": players_max,
            "player_list": java_players,
            "motd": full_motd,
        }
    except Exception:
        pass

    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        host_bytes = host.encode("utf-8")
        data = b"\x00\x00" + struct.pack(">B", len(host_bytes)) + host_bytes + struct.pack(">H", port) + b"\x01"
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

        info           = json.loads(raw.decode("utf-8"))
        players_online = info.get("players", {}).get("online", 0)
        players_max    = info.get("players", {}).get("max", 0)
        player_list    = [p.get("name", "Unknown") for p in info.get("players", {}).get("sample", [])]
        motd           = info.get("description", {})
        motd           = clean_motd(motd.get("text", "") if isinstance(motd, dict) else motd)

        return {
            "online": True,
            "players_online": players_online,
            "players_max": players_max,
            "player_list": player_list,
            "motd": motd,
        }
    except Exception:
        return {"online": False}


DISPLAY_IP = "play.shivxtreme.fun"
DISPLAY_PORT = 25565

def build_embed(info):
    if not info["online"]:
        embed = discord.Embed(
            title="🔴  SERVER OFFLINE",
            description=f"`{DISPLAY_IP}:{DISPLAY_PORT}`",
            color=0xFF0000,
        )
        embed.set_footer(text=f"Last checked: {time.strftime('%H:%M:%S')} • Powered by Lockc")
        return embed

    players = info["players_online"]
    max_p   = info["players_max"]
    names   = info["player_list"]

    if max_p > 0:
        filled = int((players / max_p) * 10)
        bar = "█" * filled + "░" * (10 - filled)
        player_field = f"**{players} / {max_p}**\n`{bar}`"
    else:
        player_field = f"**{players}**"

    embed = discord.Embed(
        title="🟢  SERVER ONLINE",
        description=f"`{DISPLAY_IP}:{DISPLAY_PORT}`",
        color=0x00FF88,
    )

    embed.add_field(name="👥 Players Online", value=player_field, inline=True)

    info_text = (
        "`⚡` Version: **1.21+**\n"
        "`🖥️` Platform: **Paper**\n"
        "`🔄` Updates: **60 sec**"
    )
    embed.add_field(name="⚡ Server Info", value=info_text, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)

    if info["motd"]:
        embed.add_field(name="📜 Server MOTD", value=f"```{info['motd']}```", inline=False)

    if names:
        player_list = "\n".join(f"🟢 `{n}`" for n in names[:15])
        if len(names) > 15:
            player_list += f"\n*+{len(names)-15} more players*"
        embed.add_field(name="👤 Online Players", value=player_list, inline=False)
    elif players > 0:
        embed.add_field(name="👤 Online Players", value=f"*{players} player(s) online*", inline=False)
    else:
        embed.add_field(name="👤 Online Players", value="*Nobody online yet*", inline=False)

    embed.set_footer(text=f"Last checked: {time.strftime('%H:%M:%S')} • Powered by Lockc")
    return embed


# ─── Bot setup ────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)

status_message = None


# ─── /status command ──────────────────────────────────────────
@tree.command(name="status", description="Check the Minecraft server status right now")
async def status_command(interaction: discord.Interaction):
    if not status_enabled:
        await interaction.response.send_message("❌ Status system is off rn!", ephemeral=True)
        return
    await interaction.response.defer()
    info  = ping_minecraft(MINECRAFT_IP, MINECRAFT_PORT)
    embed = build_embed(info)
    await interaction.followup.send(embed=embed)


# ─── /togglestatus command ────────────────────────────────────
@tree.command(name="togglestatus", description="Turn status on or off [Owner only]")
@app_commands.describe(mode="on ya off")
@app_commands.choices(mode=[
    app_commands.Choice(name="on", value="on"),
    app_commands.Choice(name="off", value="off"),
])
async def toggle_status(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    global status_enabled

    if interaction.user.id not in STATUS_CONTROL_USERS:
        await interaction.response.send_message("❌ You Don't Have Permission!", ephemeral=True)
        return

    if mode.value == "on":
        status_enabled = True
        await interaction.response.send_message("✅ Turned **ON** the status system!", ephemeral=True)
    else:
        status_enabled = False
        await interaction.response.send_message("🔴 Turned **OFF** the status system!", ephemeral=True)


# ─── Auto updater ─────────────────────────────────────────────
@tasks.loop(seconds=60)
async def update_status():
    global status_message

    if not status_enabled:
        print(f"[{time.strftime('%H:%M:%S')}] Status OFF — skipping")
        return

    channel = client.get_channel(STATUS_CHANNEL_ID)
    if channel is None:
        print(f"❌ Channel nahi mila: {STATUS_CHANNEL_ID}")
        return

    info  = ping_minecraft(MINECRAFT_IP, MINECRAFT_PORT)
    embed = build_embed(info)

    try:
        if status_message is None:
            saved_id = load_message_id()
            if saved_id:
                try:
                    status_message = await channel.fetch_message(saved_id)
                    print(f"✅ Purana message mila (ID: {saved_id})")
                except discord.NotFound:
                    status_message = None

        if status_message is None:
            status_message = await channel.send(embed=embed)
            save_message_id(status_message.id)
            print(f"📨 Naya message bheja (ID: {status_message.id})")
        else:
            await status_message.edit(embed=embed)

    except discord.NotFound:
        status_message = await channel.send(embed=embed)
        save_message_id(status_message.id)
    except Exception as e:
        print(f"❌ Error: {e}")

    state = "ONLINE" if info["online"] else "OFFLINE"
    print(f"[{time.strftime('%H:%M:%S')}] {state} — {info.get('players_online', 0)} players")


# ─── on_message ───────────────────────────────────────────────
@client.event
async def on_message(message):
    if message.author.bot:
        return

    msg = message.content.strip()
    msg_lower = msg.lower()

    # ── IP reply ──────────────────────────────────────────────
    if msg_lower == "ip":
        ip_msg = (
            "🌐 **ShivXtreme SMP — Server IPs**\n\n"
            "☕ **JAVA EDITION**\n"
            "> IP: `play.shivxtreme.fun`\n"
            "> Port: `25565`\n\n"
            "📱 **POCKET EDITION (Bedrock)**\n"
            "> IP: `pe.shivxtreme.fun`\n"
            "> Port: `19132`"
        )
        await message.reply(ip_msg)
        return

    # ── $link ─────────────────────────────────────────────────
    LINK_ALLOWED_IDS = [955503311182790726, 919913690252320778, 1029372920323113011]
    if msg_lower.startswith("$link"):
        if message.author.id not in LINK_ALLOWED_IDS:
            return
        link_msg = msg[5:].strip()
        if link_msg:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            await message.channel.send(link_msg)
        return


@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user}")
    print(f"   Monitoring: {MINECRAFT_IP}:{MINECRAFT_PORT}")
    update_status.start()


client.run(DISCORD_TOKEN)
