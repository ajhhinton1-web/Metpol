import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import re

from utils.helpers import (success_embed, error_embed, info_embed,
                           load_data, save_data, get_config, GREEN, RED, BLUE, ORANGE)


INVITE_PATTERN = re.compile(r"discord(?:\.gg|app\.com/invite|\.com/invite)/[\w-]+", re.IGNORECASE)
LINK_PATTERN   = re.compile(r"https?://\S+", re.IGNORECASE)


class Moderation(commands.Cog):
    """🔧 Auto-Mod & Logging Events"""

    def __init__(self, bot):
        self.bot    = bot
        self.config = get_config()

    async def _log(self, guild: discord.Guild, embed: discord.Embed):
        ch_id = self.config["channels"].get("logs", 0)
        if ch_id:
            ch = guild.get_channel(ch_id)
            if ch:
                await ch.send(embed=embed)

    # ── Member join ───────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self.config

        # Welcome message
        wch_id = cfg["channels"].get("welcome", 0)
        if wch_id:
            wch = member.guild.get_channel(wch_id)
            if wch:
                embed = discord.Embed(
                    title=f"👋 Welcome to {member.guild.name}!",
                    description=(
                        f"Welcome {member.mention}! 🎉\n\n"
                        f"You are member **#{member.guild.member_count}**.\n"
                        f"Please read the rules and enjoy your stay!"
                    ),
                    color=GREEN,
                    timestamp=datetime.utcnow()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                await wch.send(embed=embed)

        # Log join
        embed = discord.Embed(title="📥 Member Joined", color=GREEN, timestamp=datetime.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User",    value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        await self._log(member.guild, embed)

    # ── Member leave ──────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(title="📤 Member Left", color=ORANGE, timestamp=datetime.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=True)
        roles = " ".join(r.mention for r in member.roles[1:]) or "None"
        embed.add_field(name="Roles", value=roles, inline=False)
        await self._log(member.guild, embed)

    # ── Message delete log ────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        embed = discord.Embed(title="🗑️ Message Deleted", color=RED, timestamp=datetime.utcnow())
        embed.add_field(name="Author",  value=f"{message.author} ({message.author.id})", inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        content = message.content[:1020] if message.content else "[No text content]"
        embed.add_field(name="Content", value=content, inline=False)
        await self._log(message.guild, embed)

    # ── Message edit log ──────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = discord.Embed(title="✏️ Message Edited", color=BLUE, timestamp=datetime.utcnow())
        embed.add_field(name="Author",  value=f"{before.author} ({before.author.id})", inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before",  value=before.content[:500] or "—", inline=False)
        embed.add_field(name="After",   value=after.content[:500]  or "—", inline=False)
        embed.add_field(name="Jump",    value=f"[Jump to message]({after.jump_url})", inline=False)
        await self._log(before.guild, embed)

    # ── Auto-mod: anti-invite ─────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if message.author.guild_permissions.manage_messages:
            return

        settings = load_data("automod_settings").get(str(message.guild.id), {})

        # Anti-invite
        if settings.get("anti_invite") and INVITE_PATTERN.search(message.content):
            await message.delete()
            try:
                await message.author.send(embed=error_embed("Message Removed", "Discord invite links are not allowed in this server."))
            except Exception:
                pass
            embed = discord.Embed(title="🚫 Invite Link Removed", color=RED, timestamp=datetime.utcnow())
            embed.add_field(name="User",    value=str(message.author), inline=True)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            await self._log(message.guild, embed)
            return

        # Spam filter (basic: same message repeated)
        if settings.get("anti_spam"):
            spam_data = load_data("spam_tracker")
            uid       = str(message.author.id)
            gid       = str(message.guild.id)
            spam_data.setdefault(gid, {}).setdefault(uid, [])
            spam_data[gid][uid].append({"content": message.content, "time": datetime.utcnow().isoformat()})
            spam_data[gid][uid] = spam_data[gid][uid][-10:]  # keep last 10
            recent = [m["content"] for m in spam_data[gid][uid][-5:]]
            save_data("spam_tracker", spam_data)
            if len(recent) == 5 and len(set(recent)) == 1:
                await message.delete()
                try:
                    await message.author.timeout(discord.utils.utcnow().__class__.utcnow() + __import__("datetime").timedelta(minutes=5))
                except Exception:
                    pass
                embed = discord.Embed(title="⚠️ Spam Detected — User Muted", color=ORANGE, timestamp=datetime.utcnow())
                embed.add_field(name="User", value=str(message.author), inline=True)
                await self._log(message.guild, embed)

        await self.bot.process_commands(message)

    # ── /automod ──────────────────────────────────────────────────────────────
    automod = app_commands.Group(name="automod", description="Configure auto-moderation settings.")

    @automod.command(name="antiinvite", description="Toggle automatic removal of Discord invite links.")
    @app_commands.describe(enabled="Enable or disable")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiinvite(self, interaction: discord.Interaction, enabled: bool):
        settings = load_data("automod_settings")
        settings.setdefault(str(interaction.guild.id), {})["anti_invite"] = enabled
        save_data("automod_settings", settings)
        state = "enabled" if enabled else "disabled"
        await interaction.response.send_message(embed=success_embed(f"Anti-Invite {state.title()}", f"Invite link filtering is now **{state}**."), ephemeral=True)

    @automod.command(name="antispam", description="Toggle spam detection and auto-mute.")
    @app_commands.describe(enabled="Enable or disable")
    @app_commands.checks.has_permissions(administrator=True)
    async def antispam(self, interaction: discord.Interaction, enabled: bool):
        settings = load_data("automod_settings")
        settings.setdefault(str(interaction.guild.id), {})["anti_spam"] = enabled
        save_data("automod_settings", settings)
        state = "enabled" if enabled else "disabled"
        await interaction.response.send_message(embed=success_embed(f"Anti-Spam {state.title()}", f"Spam detection is now **{state}**."), ephemeral=True)

    @automod.command(name="status", description="Show current auto-mod settings.")
    async def status(self, interaction: discord.Interaction):
        settings = load_data("automod_settings").get(str(interaction.guild.id), {})
        embed = info_embed("Auto-Mod Settings")
        embed.add_field(name="Anti-Invite", value="✅ On" if settings.get("anti_invite") else "❌ Off", inline=True)
        embed.add_field(name="Anti-Spam",   value="✅ On" if settings.get("anti_spam")   else "❌ Off", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /poll ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="poll", description="Create a quick yes/no poll.")
    @app_commands.describe(question="The poll question", channel="Channel to post the poll")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def poll(self, interaction: discord.Interaction, question: str, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        embed  = discord.Embed(
            title="📊 Poll",
            description=f"**{question}**",
            color=BLUE,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Poll by {interaction.user}")
        msg = await target.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        await interaction.response.send_message(embed=success_embed("Poll Created!", f"Poll posted in {target.mention}."), ephemeral=True)

    # ── Role event logs ───────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return
        added   = [r for r in after.roles  if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if not added and not removed:
            return
        embed = discord.Embed(title="🔄 Member Roles Updated", color=BLUE, timestamp=datetime.utcnow())
        embed.add_field(name="Member", value=str(after), inline=True)
        if added:
            embed.add_field(name="Added",   value=" ".join(r.mention for r in added),   inline=True)
        if removed:
            embed.add_field(name="Removed", value=" ".join(r.mention for r in removed), inline=True)
        await self._log(after.guild, embed)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
