import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import json, asyncio

from utils.helpers import (success_embed, error_embed, info_embed, warn_embed,
                           load_data, save_data, get_config, BLUE, RED, GREEN, ORANGE)


# ── Permission check decorator ────────────────────────────────────────────────
def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        cfg = get_config()
        admin_role = cfg["roles"]["admin"]
        mod_role   = cfg["roles"]["moderator"]
        if interaction.user.guild_permissions.administrator:
            return True
        if any(r.name in (admin_role, mod_role) for r in interaction.user.roles):
            return True
        raise app_commands.MissingPermissions(["administrator"])
    return app_commands.check(predicate)


class Admin(commands.Cog):
    """🛡️ Admin & Moderation Commands"""

    def __init__(self, bot):
        self.bot = bot
        self.config = get_config()

    # ── Helpers ───────────────────────────────────────────────────────────────
    async def _log(self, guild: discord.Guild, embed: discord.Embed):
        ch_id = self.config["channels"].get("logs", 0)
        if ch_id:
            ch = guild.get_channel(ch_id)
            if ch:
                await ch.send(embed=embed)

    # ── /ban ──────────────────────────────────────────────────────────────────
    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(member="Member to ban", reason="Reason for ban", delete_days="Days of messages to delete (0–7)")
    @is_admin()
    async def ban(self, interaction: discord.Interaction,
                  member: discord.Member, reason: str = "No reason provided",
                  delete_days: app_commands.Range[int, 0, 7] = 0):
        await interaction.response.defer(ephemeral=True)
        if member.top_role >= interaction.user.top_role:
            return await interaction.followup.send(embed=error_embed("Hierarchy Error", "You cannot ban someone with an equal or higher role."), ephemeral=True)
        try:
            await member.send(embed=warn_embed(f"You were banned from {interaction.guild.name}", f"**Reason:** {reason}"))
        except Exception:
            pass
        await member.ban(reason=f"{reason} | Banned by {interaction.user}", delete_message_days=delete_days)
        embed = success_embed("Member Banned", f"**{member}** has been banned.\n**Reason:** {reason}")
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)
        log_embed = discord.Embed(title="🔨 Member Banned", color=RED, timestamp=datetime.utcnow())
        log_embed.add_field(name="User", value=f"{member} ({member.id})", inline=True)
        log_embed.add_field(name="Moderator", value=str(interaction.user), inline=True)
        log_embed.add_field(name="Reason", value=reason, inline=False)
        await self._log(interaction.guild, log_embed)

    # ── /unban ────────────────────────────────────────────────────────────────
    @app_commands.command(name="unban", description="Unban a user by ID.")
    @app_commands.describe(user_id="The user's Discord ID", reason="Reason for unban")
    @is_admin()
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        await interaction.response.defer(ephemeral=True)
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=reason)
            await interaction.followup.send(embed=success_embed("User Unbanned", f"**{user}** has been unbanned."), ephemeral=True)
        except discord.NotFound:
            await interaction.followup.send(embed=error_embed("Not Found", "That user is not banned or doesn't exist."), ephemeral=True)

    # ── /kick ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="Member to kick", reason="Reason for kick")
    @is_admin()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await interaction.response.defer(ephemeral=True)
        if member.top_role >= interaction.user.top_role:
            return await interaction.followup.send(embed=error_embed("Hierarchy Error", "You cannot kick someone with an equal or higher role."), ephemeral=True)
        try:
            await member.send(embed=warn_embed(f"You were kicked from {interaction.guild.name}", f"**Reason:** {reason}"))
        except Exception:
            pass
        await member.kick(reason=reason)
        await interaction.followup.send(embed=success_embed("Member Kicked", f"**{member}** has been kicked.\n**Reason:** {reason}"), ephemeral=True)
        log_embed = discord.Embed(title="👢 Member Kicked", color=ORANGE, timestamp=datetime.utcnow())
        log_embed.add_field(name="User", value=f"{member} ({member.id})", inline=True)
        log_embed.add_field(name="Moderator", value=str(interaction.user), inline=True)
        log_embed.add_field(name="Reason", value=reason, inline=False)
        await self._log(interaction.guild, log_embed)

    # ── /mute ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="mute", description="Timeout (mute) a member.")
    @app_commands.describe(member="Member to mute", duration="Duration in minutes", reason="Reason")
    @is_admin()
    async def mute(self, interaction: discord.Interaction, member: discord.Member,
                   duration: app_commands.Range[int, 1, 40320] = 10, reason: str = "No reason provided"):
        await interaction.response.defer(ephemeral=True)
        until = discord.utils.utcnow() + timedelta(minutes=duration)
        await member.timeout(until, reason=reason)
        await interaction.followup.send(embed=success_embed("Member Muted", f"**{member}** has been muted for **{duration}m**.\n**Reason:** {reason}"), ephemeral=True)
        log_embed = discord.Embed(title="🔇 Member Muted", color=ORANGE, timestamp=datetime.utcnow())
        log_embed.add_field(name="User", value=f"{member} ({member.id})", inline=True)
        log_embed.add_field(name="Duration", value=f"{duration} minutes", inline=True)
        log_embed.add_field(name="Reason", value=reason, inline=False)
        await self._log(interaction.guild, log_embed)

    # ── /unmute ───────────────────────────────────────────────────────────────
    @app_commands.command(name="unmute", description="Remove a timeout from a member.")
    @app_commands.describe(member="Member to unmute")
    @is_admin()
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        await member.timeout(None)
        await interaction.followup.send(embed=success_embed("Member Unmuted", f"**{member}**'s timeout has been removed."), ephemeral=True)

    # ── /warn ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="warn", description="Issue a warning to a member.")
    @app_commands.describe(member="Member to warn", reason="Reason for warning")
    @is_admin()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await interaction.response.defer(ephemeral=True)
        warns = load_data("warnings")
        uid   = str(member.id)
        warns.setdefault(uid, [])
        warns[uid].append({"reason": reason, "mod": str(interaction.user), "time": datetime.utcnow().isoformat()})
        save_data("warnings", warns)
        count = len(warns[uid])
        try:
            await member.send(embed=warn_embed(f"Warning #{count} in {interaction.guild.name}", f"**Reason:** {reason}"))
        except Exception:
            pass
        await interaction.followup.send(embed=success_embed("Warning Issued", f"**{member}** now has **{count}** warning(s).\n**Reason:** {reason}"), ephemeral=True)

    # ── /warnings ─────────────────────────────────────────────────────────────
    @app_commands.command(name="warnings", description="View warnings for a member.")
    @app_commands.describe(member="Member to check")
    @is_admin()
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        warns = load_data("warnings").get(str(member.id), [])
        embed = info_embed(f"Warnings for {member}", f"Total: **{len(warns)}**")
        for i, w in enumerate(warns[-10:], 1):
            embed.add_field(name=f"#{i} — {w['time'][:10]}", value=f"**{w['reason']}** | by {w['mod']}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /clearwarnings ────────────────────────────────────────────────────────
    @app_commands.command(name="clearwarnings", description="Clear all warnings for a member.")
    @app_commands.describe(member="Member to clear")
    @is_admin()
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        warns = load_data("warnings")
        warns.pop(str(member.id), None)
        save_data("warnings", warns)
        await interaction.response.send_message(embed=success_embed("Warnings Cleared", f"All warnings for **{member}** removed."), ephemeral=True)

    # ── /purge ────────────────────────────────────────────────────────────────
    @app_commands.command(name="purge", description="Bulk-delete messages in this channel.")
    @app_commands.describe(amount="Number of messages to delete (1–100)")
    @is_admin()
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100] = 10):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(embed=success_embed("Messages Purged", f"Deleted **{len(deleted)}** messages."), ephemeral=True)

    # ── /slowmode ─────────────────────────────────────────────────────────────
    @app_commands.command(name="slowmode", description="Set slowmode in the current channel.")
    @app_commands.describe(seconds="Slowmode delay in seconds (0 to disable)")
    @is_admin()
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600] = 0):
        await interaction.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await interaction.response.send_message(embed=success_embed("Slowmode Disabled"), ephemeral=True)
        else:
            await interaction.response.send_message(embed=success_embed("Slowmode Set", f"Slowmode set to **{seconds}s**."), ephemeral=True)

    # ── /lock / /unlock ───────────────────────────────────────────────────────
    @app_commands.command(name="lock", description="Lock the current channel.")
    @is_admin()
    async def lock(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message(embed=success_embed("Channel Locked", "Members can no longer send messages here."))

    @app_commands.command(name="unlock", description="Unlock the current channel.")
    @is_admin()
    async def unlock(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message(embed=success_embed("Channel Unlocked", "Members can now send messages again."))

    # ── /serverinfo ───────────────────────────────────────────────────────────
    @app_commands.command(name="serverinfo", description="Display server information.")
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        embed = discord.Embed(title=f"📊 {g.name}", color=BLUE, timestamp=datetime.utcnow())
        embed.set_thumbnail(url=g.icon.url if g.icon else discord.Embed.Empty)
        embed.add_field(name="Owner", value=str(g.owner), inline=True)
        embed.add_field(name="Members", value=str(g.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(g.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(g.roles)), inline=True)
        embed.add_field(name="Boost Level", value=str(g.premium_tier), inline=True)
        embed.add_field(name="Created", value=g.created_at.strftime("%Y-%m-%d"), inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /userinfo ─────────────────────────────────────────────────────────────
    @app_commands.command(name="userinfo", description="Display information about a user.")
    @app_commands.describe(member="Member to look up (defaults to yourself)")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        m = member or interaction.user
        embed = discord.Embed(title=f"👤 {m}", color=BLUE, timestamp=datetime.utcnow())
        embed.set_thumbnail(url=m.display_avatar.url)
        embed.add_field(name="ID", value=str(m.id), inline=True)
        embed.add_field(name="Joined Server", value=m.joined_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Account Created", value=m.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Top Role", value=m.top_role.mention, inline=True)
        warns = len(load_data("warnings").get(str(m.id), []))
        embed.add_field(name="Warnings", value=str(warns), inline=True)
        embed.add_field(name="Roles", value=" ".join(r.mention for r in m.roles[1:]) or "None", inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /announce ─────────────────────────────────────────────────────────────
    @app_commands.command(name="announce", description="Send an embedded announcement.")
    @app_commands.describe(channel="Target channel", title="Embed title", message="Embed body", color="Hex colour e.g. #FF0000")
    @is_admin()
    async def announce(self, interaction: discord.Interaction,
                       channel: discord.TextChannel, title: str, message: str, color: str = "#5865F2"):
        await interaction.response.defer(ephemeral=True)
        try:
            c = discord.Color.from_str(color)
        except ValueError:
            c = BLUE
        embed = discord.Embed(title=title, description=message, color=c, timestamp=datetime.utcnow())
        embed.set_footer(text=f"Announced by {interaction.user}")
        await channel.send(embed=embed)
        await interaction.followup.send(embed=success_embed("Announcement Sent", f"Message sent to {channel.mention}."), ephemeral=True)

    # ── /addrole / /removerole ────────────────────────────────────────────────
    @app_commands.command(name="addrole", description="Add a role to a member.")
    @app_commands.describe(member="Target member", role="Role to add")
    @is_admin()
    async def addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await member.add_roles(role, reason=f"Added by {interaction.user}")
        await interaction.response.send_message(embed=success_embed("Role Added", f"Added **{role.name}** to **{member}**."), ephemeral=True)

    @app_commands.command(name="removerole", description="Remove a role from a member.")
    @app_commands.describe(member="Target member", role="Role to remove")
    @is_admin()
    async def removerole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await member.remove_roles(role, reason=f"Removed by {interaction.user}")
        await interaction.response.send_message(embed=success_embed("Role Removed", f"Removed **{role.name}** from **{member}**."), ephemeral=True)

    # ── /nickname ─────────────────────────────────────────────────────────────
    @app_commands.command(name="nickname", description="Change a member's nickname.")
    @app_commands.describe(member="Target member", nickname="New nickname (leave blank to reset)")
    @is_admin()
    async def nickname(self, interaction: discord.Interaction, member: discord.Member, nickname: str = None):
        await member.edit(nick=nickname)
        msg = f"**{member}**'s nickname set to **{nickname}**." if nickname else f"**{member}**'s nickname reset."
        await interaction.response.send_message(embed=success_embed("Nickname Updated", msg), ephemeral=True)

    # ── /help ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="help", description="Show all available commands.")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📖 Bot Commands", color=BLUE, timestamp=datetime.utcnow())
        embed.add_field(name="🛡️ Moderation", value=(
            "`/ban` `/unban` `/kick` `/mute` `/unmute`\n"
            "`/warn` `/warnings` `/clearwarnings`\n"
            "`/purge` `/slowmode` `/lock` `/unlock`\n"
            "`/addrole` `/removerole` `/nickname`"
        ), inline=False)
        embed.add_field(name="🎟️ Tickets", value=(
            "`/ticket open` — Open a support ticket\n"
            "`/ticket close` — Close current ticket\n"
            "`/ticket add` — Add user to ticket\n"
            "`/ticket remove` — Remove user from ticket\n"
            "`/ticket setup` — Setup ticket panel"
        ), inline=False)
        embed.add_field(name="🎮 Roblox Events", value=(
            "`/event create` — Schedule an event\n"
            "`/event cancel` — Cancel an event\n"
            "`/event list` — List upcoming events\n"
            "`/event start` — Announce event start"
        ), inline=False)
        embed.add_field(name="⬆️ Roblox Ranking", value=(
            "`/rank set` — Set a user's group rank\n"
            "`/rank get` — Get a user's group rank\n"
            "`/rank promote` — Promote a user one rank\n"
            "`/rank demote` — Demote a user one rank\n"
            "`/rank exile` — Exile a user from the group"
        ), inline=False)
        embed.add_field(name="ℹ️ Info", value="`/serverinfo` `/userinfo` `/announce`", inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Admin(bot))
