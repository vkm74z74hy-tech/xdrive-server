import discord
from discord.ext import commands
from discord import app_commands
import requests

OWNER_ID   = 580924980049608714
SERVER_URL = "https://xdrive-server-production.up.railway.app"
ADMIN_KEY  = "xdrive12"   # store as env var: os.getenv("ADMIN_KEY")
BOT_TOKEN  = "MTUwMzE2MjE5OTg2NTE2MzgyOA.GD5q4M.zacQCF6qfoAHCVCiZm-giXedgnTrR3Tc77a8k4" 



# ─── Helpers ────────────────────────────────────────────────────────────────

def get_admins() -> set:
    try:
        r = requests.get(f"{SERVER_URL}/get_admins",
            params={"admin_key": ADMIN_KEY}, timeout=5)
        return set(int(x) for x in r.json().get("admins", []))
    except:
        return set()

def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    if interaction.user.id == OWNER_ID:
        return True
    return interaction.user.id in get_admins()

def status_color(days) -> discord.Color:
    if str(days).lower() == "lifetime" or days == -1:
        return discord.Color.from_str("#5865F2")   # blurple
    try:
        d = int(days)
        if d <= 3:  return discord.Color.from_str("#ED4245")   # red
        if d <= 7:  return discord.Color.from_str("#FEE75C")   # yellow
        return discord.Color.from_str("#57F287")               # green
    except:
        return discord.Color.from_str("#ED4245")

def make_status_embed(user: discord.User | None, discord_id: str, data: dict) -> discord.Embed:
    days     = data.get("days_remaining", "?")
    hwid_set = bool(data.get("hwid"))
    is_life  = str(days).lower() == "lifetime" or days == -1

    if is_life:
        title        = "✅  Unlimited Access Granted"
        description  = "Owner has granted unlimited access to this account."
        status_text  = "Unlimited access"
        expiry_text  = "None"
    else:
        try:
            d = int(days)
            if d <= 0:
                title        = "❌  Subscription Expired"
                description  = "Your subscription has expired. Contact an admin to renew."
                status_text  = "Expired"
                expiry_text  = data.get("expiry_date", "—")
            elif d <= 3:
                title        = "⚠️  Expiring Soon"
                description  = "Your subscription expires very soon. Contact an admin to renew."
                status_text  = f"**{d}** day{'s' if d != 1 else ''} remaining"
                expiry_text  = data.get("expiry_date", "—")
            else:
                title        = "✅  Subscription Active"
                description  = "Your xDrive subscription is active."
                status_text  = f"**{d}** days remaining"
                expiry_text  = data.get("expiry_date", "—")
        except:
            title        = "❓  Status Unknown"
            description  = "Could not read subscription data."
            status_text  = "Unknown"
            expiry_text  = "—"

    embed = discord.Embed(
        title=title,
        description=description,
        color=status_color(days)
    )

    display = f"@{user.name}" if user else f"`{discord_id}`"
    embed.add_field(name="User",   value=display,       inline=False)
    embed.add_field(name="Status", value=status_text,   inline=False)
    embed.add_field(name="Expiry", value=expiry_text,   inline=False)

    if user and user.avatar:
        embed.set_thumbnail(url=user.avatar.url)

    embed.set_footer(text="xDrive • PS Edition")
    return embed


# ─── Bot setup ──────────────────────────────────────────────────────────────

intents = discord.Intents.default()
bot  = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# ─── /checkdays  (everyone) ─────────────────────────────────────────────────

@tree.command(name="checkdays", description="Check your xDrive subscription status")
async def checkdays(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    discord_id = str(interaction.user.id)
    try:
        r = requests.get(f"{SERVER_URL}/check_user",
            params={"discord_id": discord_id, "admin_key": ADMIN_KEY}, timeout=5)
        data = r.json()
    except:
        await interaction.followup.send("❌ Could not reach the license server.", ephemeral=True)
        return

    if not data.get("ok"):
        embed = discord.Embed(
            title="❌  No Subscription Found",
            description="You don't have an active xDrive subscription.\nContact an admin to get access.",
            color=discord.Color.from_str("#ED4245")
        )
        embed.set_footer(text="xDrive • PS Edition")
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    embed = make_status_embed(interaction.user, discord_id, data)
    await interaction.followup.send(embed=embed, ephemeral=True)


# ─── /checkuser  (admin) ────────────────────────────────────────────────────

@tree.command(name="checkuser", description="[ADMIN] Check any user's subscription")
@app_commands.describe(discord_id="Target's Discord user ID")
async def checkuser(interaction: discord.Interaction, discord_id: str):
    if not is_admin_or_owner(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        r = requests.get(f"{SERVER_URL}/check_user",
            params={"discord_id": discord_id, "admin_key": ADMIN_KEY}, timeout=5)
        data = r.json()
    except:
        await interaction.followup.send("❌ Could not reach the license server.", ephemeral=True)
        return

    if not data.get("ok"):
        await interaction.followup.send(f"❌ No user found with ID `{discord_id}`.", ephemeral=True)
        return

    try:
        target = await bot.fetch_user(int(discord_id))
    except:
        target = None

    embed = make_status_embed(target, discord_id, data)
    # Admins also see the HWID status
    hwid_val = "🔒 Locked" if data.get("hwid") else "🔓 Not set (no login yet)"
    embed.add_field(name="HWID", value=hwid_val, inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)


# ─── /adddays  (admin) ──────────────────────────────────────────────────────

@tree.command(name="adddays", description="[ADMIN] Add days to a user's subscription")
@app_commands.describe(discord_id="Target's Discord user ID", days="Days to add")
async def adddays(interaction: discord.Interaction, discord_id: str, days: int):
    if not is_admin_or_owner(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        r = requests.post(f"{SERVER_URL}/add_days",
            json={"discord_id": discord_id, "days": days, "admin_key": ADMIN_KEY}, timeout=5)
        data = r.json()
    except:
        await interaction.followup.send("❌ Could not reach the license server.", ephemeral=True)
        return

    if data.get("ok"):
        embed = discord.Embed(title="✅  Days Added", color=discord.Color.from_str("#57F287"))
        embed.add_field(name="User",      value=f"`{discord_id}`",                  inline=False)
        embed.add_field(name="Added",     value=f"**+{days}** days",                inline=True)
        embed.add_field(name="New Total", value=f"**{data['total_days']}** days",   inline=True)
        embed.set_footer(text=f"Added by {interaction.user.name} • xDrive")
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send(f"❌ {data.get('message', 'Failed')}", ephemeral=True)


# ─── /removedays  (admin) ───────────────────────────────────────────────────

@tree.command(name="removedays", description="[ADMIN] Remove days from a user's subscription")
@app_commands.describe(discord_id="Target's Discord user ID", days="Days to remove")
async def removedays(interaction: discord.Interaction, discord_id: str, days: int):
    if not is_admin_or_owner(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        r = requests.post(f"{SERVER_URL}/remove_days",
            json={"discord_id": discord_id, "days": days, "admin_key": ADMIN_KEY}, timeout=5)
        data = r.json()
    except:
        await interaction.followup.send("❌ Could not reach the license server.", ephemeral=True)
        return

    if data.get("ok"):
        embed = discord.Embed(title="✅  Days Removed", color=discord.Color.from_str("#FEE75C"))
        embed.add_field(name="User",      value=f"`{discord_id}`",                  inline=False)
        embed.add_field(name="Removed",   value=f"**-{days}** days",                inline=True)
        embed.add_field(name="New Total", value=f"**{data['total_days']}** days",   inline=True)
        embed.set_footer(text=f"Removed by {interaction.user.name} • xDrive")
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send(f"❌ {data.get('message', 'Failed')}", ephemeral=True)


# ─── /resethwid  (admin) ────────────────────────────────────────────────────

@tree.command(name="resethwid", description="[ADMIN] Reset a user's HWID so they can log in on a new PC")
@app_commands.describe(discord_id="Target's Discord user ID")
async def resethwid(interaction: discord.Interaction, discord_id: str):
    if not is_admin_or_owner(interaction):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        r = requests.post(f"{SERVER_URL}/reset_hwid",
            json={"discord_id": discord_id, "admin_key": ADMIN_KEY}, timeout=5)
        data = r.json()
    except:
        await interaction.followup.send("❌ Could not reach the license server.", ephemeral=True)
        return

    if data.get("ok"):
        embed = discord.Embed(
            title="🔓  HWID Reset",
            description=f"HWID cleared for `{discord_id}`.\nTheir next login will lock to their new PC.",
            color=discord.Color.from_str("#5865F2")
        )
        embed.set_footer(text=f"Reset by {interaction.user.name} • xDrive")
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send(f"❌ {data.get('message', 'Failed')}", ephemeral=True)


# ─── /addadmin  (owner only — 580924980049608714) ───────────────────────────

@tree.command(name="addadmin", description="[OWNER ONLY] Promote a user to admin")
@app_commands.describe(discord_id="Discord user ID to promote")
async def addadmin(interaction: discord.Interaction, discord_id: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        r = requests.post(f"{SERVER_URL}/add_admin",
            json={"discord_id": discord_id, "admin_key": ADMIN_KEY}, timeout=5)
        data = r.json()
    except:
        await interaction.followup.send("❌ Could not reach the license server.", ephemeral=True)
        return

    if data.get("ok"):
        embed = discord.Embed(
            title="⭐  Admin Added",
            description=f"`{discord_id}` can now manage user subscriptions.",
            color=discord.Color.from_str("#57F287")
        )
        embed.set_footer(text="xDrive • PS Edition")
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send(f"❌ {data.get('message', 'Failed')}", ephemeral=True)


# ─── Startup ────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ xDrive bot online as {bot.user}")

bot.run(BOT_TOKEN)
