"""
Roblox Ranking System
─────────────────────
Uses the Roblox Open Cloud API (preferred) OR falls back to the cookie-based
legacy endpoint.  Fill in config.json with your details.

Required config keys:
  roblox.cookie   — your .ROBLOSECURITY cookie (for legacy endpoint)
  roblox.group_id — your Roblox group ID
  roblox.rank_names — mapping of rank ID (str) to display name
"""

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp, asyncio
from datetime import datetime

from utils.helpers import (success_embed, error_embed, info_embed,
                           load_data, save_data, get_config, GREEN, RED, BLUE, ORANGE)


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        cfg = get_config()
        admin_role = cfg["roles"].get("admin", "Admin")
        mod_role   = cfg["roles"].get("moderator", "Moderator")
        if interaction.user.guild_permissions.administrator:
            return True
        if any(r.name in (admin_role, mod_role) for r in interaction.user.roles):
            return True
        raise app_commands.MissingPermissions(["administrator"])
    return app_commands.check(predicate)


# ── Roblox API Wrapper ────────────────────────────────────────────────────────
class RobloxAPI:
    BASE        = "https://api.roblox.com"
    GROUPS_BASE = "https://groups.roblox.com"
    USERS_BASE  = "https://users.roblox.com"
    AUTH_BASE   = "https://auth.roblox.com"

    def __init__(self, cookie: str, group_id: int):
        self.cookie   = cookie
        self.group_id = group_id
        self._token   = None
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                cookies={".ROBLOSECURITY": self.cookie},
                headers={"User-Agent": "Mozilla/5.0"}
            )
        return self._session

    async def _get_csrf(self) -> str:
        """Fetch a fresh X-CSRF-TOKEN."""
        session = await self._get_session()
        async with session.post(f"{self.AUTH_BASE}/v2/logout") as r:
            token = r.headers.get("x-csrf-token")
            if token:
                self._token = token
        return self._token or ""

    async def _post(self, url: str, payload: dict) -> dict:
        token   = await self._get_csrf()
        session = await self._get_session()
        async with session.post(url, json=payload, headers={"X-CSRF-TOKEN": token}) as r:
            return {"status": r.status, "data": await r.json()}

    async def _get(self, url: str) -> dict:
        session = await self._get_session()
        async with session.get(url) as r:
            return {"status": r.status, "data": await r.json()}

    # ── User resolution ───────────────────────────────────────────────────────
    async def get_user_id(self, username: str) -> int | None:
        r = await self._post(f"{self.USERS_BASE}/v1/usernames/users",
                             {"usernames": [username], "excludeBannedUsers": False})
        data = r["data"].get("data", [])
        return data[0]["id"] if data else None

    async def get_username(self, user_id: int) -> str | None:
        r = await self._get(f"{self.USERS_BASE}/v1/users/{user_id}")
        return r["data"].get("name")

    # ── Group info ────────────────────────────────────────────────────────────
    async def get_group_roles(self) -> list[dict]:
        r = await self._get(f"{self.GROUPS_BASE}/v1/groups/{self.group_id}/roles")
        return r["data"].get("roles", [])

    async def get_member_role(self, user_id: int) -> dict | None:
        r = await self._get(f"{self.GROUPS_BASE}/v1/users/{user_id}/groups/roles")
        groups = r["data"].get("data", [])
        for g in groups:
            if g.get("group", {}).get("id") == self.group_id:
                return g.get("role")
        return None

    # ── Ranking ───────────────────────────────────────────────────────────────
    async def set_rank(self, user_id: int, rank_id: int) -> dict:
        return await self._patch_rank(user_id, rank_id)

    async def _patch_rank(self, user_id: int, rank_id: int) -> dict:
        token   = await self._get_csrf()
        session = await self._get_session()
        url     = f"{self.GROUPS_BASE}/v1/groups/{self.group_id}/users/{user_id}"
        async with session.patch(url, json={"roleId": rank_id}, headers={"X-CSRF-TOKEN": token}) as r:
            return {"status": r.status, "data": await r.json() if r.content_type == "application/json" else {}}

    async def exile(self, user_id: int) -> dict:
        token   = await self._get_csrf()
        session = await self._get_session()
        url     = f"{self.GROUPS_BASE}/v1/groups/{self.group_id}/users/{user_id}"
        async with session.delete(url, headers={"X-CSRF-TOKEN": token}) as r:
            return {"status": r.status}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ── Cog ───────────────────────────────────────────────────────────────────────
class RobloxRanking(commands.Cog):
    """⬆️ Roblox Group Ranking"""

    def __init__(self, bot):
        self.bot    = bot
        cfg         = get_config()
        rb          = cfg.get("roblox", {})
        self.api    = RobloxAPI(rb.get("cookie", ""), rb.get("group_id", 0))
        self.config = cfg
        self._roles_cache: list[dict] = []

    async def cog_unload(self):
        await self.api.close()

    async def _log_rank_action(self, guild: discord.Guild, action: str, mod: discord.Member,
                                roblox_user: str, old_rank: str, new_rank: str):
        log_ch_id = self.config["channels"].get("ranking_logs", 0)
        if not log_ch_id:
            return
        ch = guild.get_channel(log_ch_id)
        if not ch:
            return
        embed = discord.Embed(title=f"⬆️ Rank {action}", color=GREEN, timestamp=datetime.utcnow())
        embed.add_field(name="Roblox User",  value=roblox_user,     inline=True)
        embed.add_field(name="Moderator",    value=str(mod),         inline=True)
        embed.add_field(name="Old Rank",     value=old_rank or "N/A",inline=True)
        embed.add_field(name="New Rank",     value=new_rank,         inline=True)
        await ch.send(embed=embed)

    async def _get_roles(self) -> list[dict]:
        if not self._roles_cache:
            self._roles_cache = await self.api.get_group_roles()
        return self._roles_cache

    async def _resolve_user(self, interaction: discord.Interaction, username: str) -> int | None:
        uid = await self.api.get_user_id(username)
        if not uid:
            await interaction.followup.send(embed=error_embed("User Not Found", f"No Roblox user named `{username}`."), ephemeral=True)
        return uid

    rank = app_commands.Group(name="rank", description="Roblox group ranking commands.")

    # ── /rank get ─────────────────────────────────────────────────────────────
    @rank.command(name="get", description="Get a Roblox user's current group rank.")
    @app_commands.describe(username="Roblox username")
    @is_admin()
    async def get(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer(ephemeral=True)
        uid  = await self._resolve_user(interaction, username)
        if not uid:
            return
        role = await self.api.get_member_role(uid)
        if not role:
            return await interaction.followup.send(embed=error_embed("Not in Group", f"**{username}** is not a member of this group."), ephemeral=True)
        embed = info_embed(f"Rank — {username}",
                           f"**{username}** has rank **{role['name']}** (Rank ID: `{role['rank']}`).")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /rank set ─────────────────────────────────────────────────────────────
    @rank.command(name="set", description="Set a Roblox user's rank by rank ID.")
    @app_commands.describe(username="Roblox username", rank_id="The role rank ID (1–255)")
    @is_admin()
    async def set(self, interaction: discord.Interaction, username: str, rank_id: int):
        await interaction.response.defer(ephemeral=True)
        uid = await self._resolve_user(interaction, username)
        if not uid:
            return

        old_role = await self.api.get_member_role(uid)
        old_name = old_role["name"] if old_role else "Not in group"

        # Find role ID from rank number
        roles     = await self._get_roles()
        target    = next((r for r in roles if r["rank"] == rank_id), None)
        if not target:
            return await interaction.followup.send(embed=error_embed("Invalid Rank", f"No role with rank ID `{rank_id}` found in the group."), ephemeral=True)

        result = await self.api.set_rank(uid, target["id"])
        if result["status"] == 200:
            await interaction.followup.send(embed=success_embed("Rank Set", f"**{username}** → **{target['name']}** (Rank {rank_id})"), ephemeral=True)
            await self._log_rank_action(interaction.guild, "Set", interaction.user, username, old_name, target["name"])
        else:
            await interaction.followup.send(embed=error_embed("API Error", f"Failed to set rank. Status: `{result['status']}`\n```{result.get('data',{})}```"), ephemeral=True)

    # ── /rank promote ─────────────────────────────────────────────────────────
    @rank.command(name="promote", description="Promote a Roblox user one rank.")
    @app_commands.describe(username="Roblox username")
    @is_admin()
    async def promote(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer(ephemeral=True)
        uid = await self._resolve_user(interaction, username)
        if not uid:
            return
        current = await self.api.get_member_role(uid)
        if not current:
            return await interaction.followup.send(embed=error_embed("Not in Group", f"**{username}** is not in the group."), ephemeral=True)

        roles  = sorted(await self._get_roles(), key=lambda r: r["rank"])
        c_rank = current["rank"]
        above  = [r for r in roles if r["rank"] > c_rank and r["rank"] < 255]
        if not above:
            return await interaction.followup.send(embed=error_embed("Already Max Rank", f"**{username}** is already at the highest promotable rank."), ephemeral=True)

        next_role = above[0]
        result    = await self.api.set_rank(uid, next_role["id"])
        if result["status"] == 200:
            await interaction.followup.send(embed=success_embed("Promoted!", f"**{username}** promoted:\n`{current['name']}` → `{next_role['name']}`"), ephemeral=True)
            await self._log_rank_action(interaction.guild, "Promote", interaction.user, username, current["name"], next_role["name"])
        else:
            await interaction.followup.send(embed=error_embed("API Error", f"Status: `{result['status']}`"), ephemeral=True)

    # ── /rank demote ──────────────────────────────────────────────────────────
    @rank.command(name="demote", description="Demote a Roblox user one rank.")
    @app_commands.describe(username="Roblox username")
    @is_admin()
    async def demote(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer(ephemeral=True)
        uid = await self._resolve_user(interaction, username)
        if not uid:
            return
        current = await self.api.get_member_role(uid)
        if not current:
            return await interaction.followup.send(embed=error_embed("Not in Group", f"**{username}** is not in the group."), ephemeral=True)

        roles  = sorted(await self._get_roles(), key=lambda r: r["rank"])
        c_rank = current["rank"]
        below  = [r for r in roles if r["rank"] < c_rank and r["rank"] > 0]
        if not below:
            return await interaction.followup.send(embed=error_embed("Already Lowest Rank"), ephemeral=True)

        prev_role = below[-1]
        result    = await self.api.set_rank(uid, prev_role["id"])
        if result["status"] == 200:
            await interaction.followup.send(embed=success_embed("Demoted", f"**{username}** demoted:\n`{current['name']}` → `{prev_role['name']}`"), ephemeral=True)
            await self._log_rank_action(interaction.guild, "Demote", interaction.user, username, current["name"], prev_role["name"])
        else:
            await interaction.followup.send(embed=error_embed("API Error", f"Status: `{result['status']}`"), ephemeral=True)

    # ── /rank exile ───────────────────────────────────────────────────────────
    @rank.command(name="exile", description="Exile (kick) a Roblox user from the group.")
    @app_commands.describe(username="Roblox username")
    @app_commands.checks.has_permissions(administrator=True)
    async def exile(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer(ephemeral=True)
        uid = await self._resolve_user(interaction, username)
        if not uid:
            return
        old = await self.api.get_member_role(uid)
        result = await self.api.exile(uid)
        if result["status"] == 200:
            await interaction.followup.send(embed=success_embed("User Exiled", f"**{username}** has been removed from the group."), ephemeral=True)
            await self._log_rank_action(interaction.guild, "Exile", interaction.user, username, old["name"] if old else "Unknown", "Exiled")
        else:
            await interaction.followup.send(embed=error_embed("API Error", f"Status: `{result['status']}`"), ephemeral=True)

    # ── /rank list ────────────────────────────────────────────────────────────
    @rank.command(name="list", description="List all ranks in the Roblox group.")
    async def list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            roles = sorted(await self._get_roles(), key=lambda r: r["rank"])
        except Exception as e:
            return await interaction.followup.send(embed=error_embed("API Error", str(e)), ephemeral=True)
        embed = info_embed("Group Ranks", f"Total: **{len(roles)}** roles")
        for r in roles:
            embed.add_field(name=f"Rank {r['rank']} — {r['name']}", value=f"ID: `{r['id']}`", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /rank verify ──────────────────────────────────────────────────────────
    @rank.command(name="verify", description="Link your Discord to a Roblox account (saves the link).")
    @app_commands.describe(username="Your Roblox username")
    async def verify(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer(ephemeral=True)
        uid = await self.api.get_user_id(username)
        if not uid:
            return await interaction.followup.send(embed=error_embed("Not Found", f"No Roblox user named `{username}`."), ephemeral=True)

        links = load_data("roblox_links")
        links[str(interaction.user.id)] = {"roblox_id": uid, "username": username}
        save_data("roblox_links", links)

        role_name = self.config["roles"].get("verified", "Verified")
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if role:
            await interaction.user.add_roles(role)

        await interaction.followup.send(embed=success_embed("Verified!", f"Linked Discord → Roblox: **{username}** (ID: `{uid}`)"), ephemeral=True)

    # ── /rank whois ───────────────────────────────────────────────────────────
    @rank.command(name="whois", description="Look up a Discord member's linked Roblox account.")
    @app_commands.describe(member="Discord member to look up")
    async def whois(self, interaction: discord.Interaction, member: discord.Member = None):
        m     = member or interaction.user
        links = load_data("roblox_links")
        link  = links.get(str(m.id))
        if not link:
            return await interaction.response.send_message(embed=error_embed("Not Verified", f"**{m}** has not linked a Roblox account."), ephemeral=True)
        role = await self.api.get_member_role(link["roblox_id"])
        embed = info_embed(f"Roblox Info — {m.display_name}",
                           f"Roblox Username: **{link['username']}**\nRoblox ID: `{link['roblox_id']}`\n"
                           f"Group Rank: **{role['name'] if role else 'Not in group'}**")
        embed.set_thumbnail(url=m.display_avatar.url)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(RobloxRanking(bot))
