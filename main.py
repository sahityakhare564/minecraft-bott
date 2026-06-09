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
MINECRAFT_PORT    = 19132
DISCORD_TOKEN     = os.environ.get("DISCORD_TOKEN")
STATUS_CHANNEL_ID = 1439258136278995026

# Sirf yeh roles /sudo_rm_rf use kar sakte hain
ALLOWED_ROLES = ["Admin", "Owner", "Moderator"]
# ============================================================

MESSAGE_ID_FILE = "/tmp/status_message_id.txt"


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
        color=discord.Color.red(),
    )
    embed.add_field(name="👥 Players", value=f"**{players} / {max_p}**", inline=True)

    if names:
        embed.add_field(name="🧍 Online Now", value="\n".join(f"• {n}" for n in names), inline=True)
    elif players > 0:
        embed.add_field(name="🧍 Online Now", value=f"{players} player(s) (names hidden)", inline=True)
    else:
        embed.add_field(name="🧍 Online Now", value="Nobody online yet", inline=True)

    if info["motd"]:
        embed.add_field(name="📋 MOTD", value=info["motd"], inline=False)

    embed.set_footer(text=f"Updates every 60 sec • Last checked: {time.strftime('%H:%M:%S')}")
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
    await interaction.response.defer()
    info  = ping_minecraft(MINECRAFT_IP, MINECRAFT_PORT)
    embed = build_embed(info)
    await interaction.followup.send(embed=embed)


# ─── /sudo_rm_rf prank command 😈 ────────────────────────────
@tree.command(name="sudo_rm_rf", description="⚠️ Admin only - System maintenance tool")
async def sudo_rm_rf_command(interaction: discord.Interaction):

    if ALLOWED_ROLES:
        user_roles = [r.name for r in interaction.user.roles]
        if not any(role in user_roles for role in ALLOWED_ROLES):
            await interaction.response.send_message(
                "❌ Tere paas permission nahi hai!", ephemeral=True
            )
            return

    await interaction.response.defer()

    fake_ips = ["185.234.218.51", "103.45.67.12", "92.168.1.103",
                "77.88.55.66", "198.51.100.42", "203.0.113.99"]
    fake_usernames = ["xX_H4CK3R_Xx", "D4RKN3T_B0T", "R00T_ACCESS",
                      "ANON_GHOST", "CYB3R_CR1M3", "SKID_LORD_69"]
    hacker_ip   = random.choice(fake_ips)
    hacker_name = random.choice(fake_usernames)

    # Phase 1
    msg = await interaction.followup.send("💻 `root@shivxtreme:~# sudo rm -rf /*`")
    await asyncio.sleep(1)
    await msg.edit(content=(
        "💻 `root@shivxtreme:~# sudo rm -rf /*`\n"
        "`[sudo] password for root: ••••••••`"
    ))
    await asyncio.sleep(1)
    await msg.edit(content=(
        "💻 `root@shivxtreme:~# sudo rm -rf /*`\n"
        "`[sudo] password for root: ••••••••`\n"
        "`Initializing... ⚙️`"
    ))
    await asyncio.sleep(2)

    # Phase 2
    files = [
        "/bin/sh",
        "/etc/passwd",
        "/var/minecraft",
        f"/home/players  ({random.randint(1000,5000)} files)",
        "/world/data",
        "/plugins",
        "/server.properties",
    ]
    text = "⚠️ **DELETING SYSTEM FILES...**\n"
    await msg.edit(content=text)
    await asyncio.sleep(1)

    for f in files:
        text += f"`removing {f}...` ❌ **[ DELETED ]**\n"
        await msg.edit(content=text)
        await asyncio.sleep(1)

    await asyncio.sleep(1)

    # Phase 3
    await msg.edit(content=(
        "💀 **CRITICAL SYSTEM FAILURE**\n"
        "`[PANIC] Kernel modules destroyed!`\n"
        "`[PANIC] Player data: WIPED`\n"
        "`[PANIC] World files: CORRUPTED`\n"
        "`[PANIC] Server config: GONE`\n"
        "`[FATAL] System is going down NOW!`\n"
        f"`Executed by: {hacker_name} @ {hacker_ip}`\n"
        f"~~`{MINECRAFT_IP}`~~ → `OFFLINE` 💀\n"
        "**RIP ShivXtreme SMP 🪦**"
    ))
    await asyncio.sleep(4)

    # Phase 4
    await msg.edit(content=(
        f"😂 gotchu guys every thing is totally fine\n"
        f"🎭 Pranked by {interaction.user.mention} 😈"
    ))


# ─── Auto updater ─────────────────────────────────────────────
@tasks.loop(seconds=60)
async def update_status():
    global status_message

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


@client.event
async def on_message(message):
    if message.author.bot:
        return
    if message.content.strip().lower() == "ip":
        ip_msg = f"🌐 **ShivXtreme SMP**\n**IP:** `{MINECRAFT_IP}`\n**Port:** `{MINECRAFT_PORT}`"
        await message.reply(ip_msg)

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user}")
    print(f"   Monitoring: {MINECRAFT_IP}:{MINECRAFT_PORT}")
    update_status.start()


client.run(DISCORD_TOKEN)
