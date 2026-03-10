import discord
from discord.ext import commands
from discord import app_commands
import os
import logging
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

import settings  # ← all user-editable config lives here

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("Bot")

# ── Load secrets from Replit Secrets (env vars) ───────────────────────────────
DISCORD_TOKEN  = os.environ.get("DISCORD_TOKEN", "")
ROBLOX_COOKIE  = os.environ.get("ROBLOX_COOKIE", "")

if not DISCORD_TOKEN:
    raise ValueError(
        "\n\n  No Discord token found!\n"
        "  Go to Replit → Tools → Secrets and add:\n"
        "    Key:   DISCORD_TOKEN\n"
        "    Value: your bot token\n"
    )

# Build the merged config dict (settings.py values + secrets)
config = settings.build_config(token=DISCORD_TOKEN, roblox_cookie=ROBLOX_COOKIE)

# ── Keep-alive server (prevents Replit free tier from sleeping) ───────────────
class _PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

    def log_message(self, *args):
        pass


def run_keepalive(port: int = 8080):
    server = HTTPServer(("0.0.0.0", port), _PingHandler)
    log.info(f"Keep-alive server running on port {port}")
    server.serve_forever()

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members         = True
intents.message_content = True
intents.guilds          = True


class AdminBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        cogs = [
            "cogs.admin",
            "cogs.tickets",
            "cogs.roblox_events",
            "cogs.roblox_ranking",
            "cogs.moderation",
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                log.info(f"Loaded: {cog}")
            except Exception as e:
                log.error(f"Failed to load {cog}: {e}")

        guild_id = config.get("guild_id") or 0
        if guild_id:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info(f"Slash commands synced to guild {guild_id} (instant).")
        else:
            await self.tree.sync()
            log.info("Slash commands synced globally (up to 1hr).")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="over the server | /help",
            )
        )


bot = AdminBot()


# ── Global slash command error handler ───────────────────────────────────────
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        embed = discord.Embed(title="❌ Missing Permissions",
                              description="You don't have permission to use this command.",
                              color=discord.Color.red())
    elif isinstance(error, app_commands.CommandOnCooldown):
        embed = discord.Embed(title="⏳ Cooldown",
                              description=f"Wait **{error.retry_after:.1f}s** before using this again.",
                              color=discord.Color.orange())
    else:
        log.error(f"Slash command error in /{interaction.command}: {error}")
        embed = discord.Embed(title="❌ Error",
                              description=f"An unexpected error occurred:\n```{error}```",
                              color=discord.Color.red())
    if not interaction.response.is_done():
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send(embed=embed, ephemeral=True)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    Thread(target=run_keepalive, daemon=True).start()
    bot.run(config["token"])
