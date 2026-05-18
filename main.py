import discord
from discord.ext import tasks
from discord import app_commands
import socket
import struct
import json
import time
import os
import re
 
# ============================================================
#   EDIT THESE 3 THINGS ONLY
# ============================================================
MINECRAFT_IP   = "play.shivxtreme.fun"
MINECRAFT_PORT = 19132
DISCORD_TOKEN  = os.environ.get("DISCORD_TOKEN")
# ============================================================
 
STATUS_CHANNEL_ID = 1439258136278995026
MESSAGE_ID_FILE   = "/tmp/status_message_id.txt"
 
 
# ─── MOTD cleaner (§a §l jaise color codes hatao) ─────────────
def clean_motd(text):
    return re.sub(r'§.', '', str(text)).strip()
 
 
# ─── Ping (Bedrock UDP → Java TCP fallback) ───────────────────
def ping_minecraft(host, port, timeout=5):
 
    # ── Bedrock UDP ping ──────────────────────────────────────
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
 
        # Skip: 1 (ID) + 8 (time) + 8 (guid) + 16 (magic) + 2 (str len)
        offset  = 1 + 8 + 8 + 16 + 2
        raw_str = data[offset:].decode("utf-8", errors="ignore")
 
        # Format: MCPE;MOTD;protocol;version;players;max;serverid;sub_motd;...
        parts          = raw_str.split(";")
        motd           = clean_motd(parts[1]) if len(parts) > 1 else ""
        sub_motd       = clean_motd(parts[7]) if len(parts) > 7 else ""
        players_online = int(parts[4]) if len(parts) > 4 else 0
        players_max    = int(parts[5]) if len(parts) > 5 else 0
        full_motd      = f"{motd} | {sub_motd}" if sub_motd else motd
 
        return {
            "online": True,
            "players_online": players_online,
            "players_max": players_max,
            "player_list": [],
            "motd": full_motd,
        }
 
    except Exception:
        pass  # Bedrock fail → Java try karo
 
    # ── Java TCP ping (fallback) ──────────────────────────────
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
 
 
# ─── Embed builder ────────────────────────────────────────────
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
        color=discord.Color.red(),   # ← RED color
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
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)
 
status_message = None
 
 
def save_message_id(msg_id: int):
    with open(MESSAGE_ID_FILE, "w") as f:
        f.write(str(msg_id))
 
 
def load_message_id():
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
                    print(f"✅ Purana message fetch kiya (ID: {saved_id})")
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
        print(f"📨 Delete tha, naya bheja (ID: {status_message.id})")
    except Exception as e:
        print(f"❌ Error: {e}")
 
    state = "ONLINE" if info["online"] else "OFFLINE"
    print(f"[{time.strftime('%H:%M:%S')}] {state} — {info.get('players_online', 0)} players | MOTD: {info.get('motd', 'N/A')}")
 
 
@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user}")
    print(f"   Monitoring: {MINECRAFT_IP}:{MINECRAFT_PORT}")
    update_status.start()
 
 
client.run(DISCORD_TOKEN)
 
