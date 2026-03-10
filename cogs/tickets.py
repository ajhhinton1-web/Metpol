import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import asyncio, io, json, os

from utils.helpers import (success_embed, error_embed, info_embed, warn_embed,
                           load_data, save_data, get_config, GREEN, RED, BLUE, CYAN, ORANGE, PURPLE)

# ── Tier metadata (labels / emojis only — role IDs come from config.json) ─────
ESCALATION_TIERS = [
    {
        "level":       1,
        "label":       "Superintendent+",
        "description": "Initial support tier — Superintendent & above",
        "emoji":       "🟢",
    },
    {
        "level":       2,
        "label":       "Deputy Assistant Commissioner+",
        "description": "First escalation — Deputy Assistant Commissioner & above",
        "emoji":       "🟡",
    },
    {
        "level":       3,
        "label":       "Deputy Commissioner+",
        "description": "Final escalation — Deputy Commissioner & above",
        "emoji":       "🔴",
    },
]

ESCALATION_COLORS = {1: CYAN, 2: ORANGE, 3: RED}
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


# ── Config helpers (read/write tier_role_ids live) ────────────────────────────
def _read_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)

def _write_config(cfg: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def get_tier_role_ids(level: int) -> list[int]:
    """Return the list of Discord role IDs configured for a tier level."""
    try:
        cfg = _read_config()
        ids = cfg["ticket"]["tier_role_ids"].get(str(level), [])
        return [int(i) for i in ids]
    except Exception:
        return []

def set_tier_role_ids(level: int, ids: list[int]):
    """Persist updated role ID list for a tier level."""
    cfg = _read_config()
    cfg["ticket"]["tier_role_ids"][str(level)] = ids
    _write_config(cfg)

def all_tier_role_ids_up_to(level: int) -> list[int]:
    """
    Returns combined role IDs for all tiers from `level` up to the max.
    (Higher tiers are supersets, so a Tier-3 role can also handle Tier-1 tickets.)
    """
    ids: set[int] = set()
    for lvl in range(level, len(ESCALATION_TIERS) + 1):
        ids.update(get_tier_role_ids(lvl))
    return list(ids)


# ── Tier-based permission helpers ─────────────────────────────────────────────
def get_member_tier(member: discord.Member) -> int:
    """Return the highest tier this member qualifies for based on their role IDs (0 = none)."""
    if member.guild_permissions.administrator:
        return len(ESCALATION_TIERS)
    member_role_ids = {r.id for r in member.roles}
    best = 0
    for tier in ESCALATION_TIERS:
        if member_role_ids & set(get_tier_role_ids(tier["level"])):
            best = tier["level"]
    return best

def can_handle_ticket(member: discord.Member, ticket_level: int) -> bool:
    return get_member_tier(member) >= ticket_level


# ── Ticket Panel View (persistent) ────────────────────────────────────────────
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎟️  Open a Ticket", style=discord.ButtonStyle.primary, custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=info_embed("Open a Ticket", "Please select a category for your ticket:"),
            view=CategoryView(),
            ephemeral=True,
        )


# ── Ticket Control View ───────────────────────────────────────────────────────
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await TicketSystem.close_ticket(interaction)

    @discord.ui.button(label="📄 Transcript", style=discord.ButtonStyle.secondary, custom_id="ticket:transcript")
    async def transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        await TicketSystem.send_transcript(interaction)

    @discord.ui.button(label="⬆️ Escalate", style=discord.ButtonStyle.primary, custom_id="ticket:escalate_btn")
    async def escalate_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        tickets = load_data("tickets")
        ticket  = tickets.get(str(interaction.channel.id))
        if not ticket:
            return await interaction.response.send_message(
                embed=error_embed("Not a Ticket", "This can only be used inside a ticket channel."),
                ephemeral=True,
            )
        current_level = ticket.get("escalation_level", 1)
        if current_level >= len(ESCALATION_TIERS):
            return await interaction.response.send_message(
                embed=error_embed(
                    "Already at Final Escalation",
                    f"This ticket is already at **{ESCALATION_TIERS[-1]['emoji']} "
                    f"{ESCALATION_TIERS[-1]['label']}**. No further escalation is possible."
                ),
                ephemeral=True,
            )
        if not can_handle_ticket(interaction.user, current_level):
            req  = ESCALATION_TIERS[current_level - 1]
            mine = get_member_tier(interaction.user)
            my_label = ESCALATION_TIERS[mine - 1]["label"] if mine > 0 else "No qualifying role"
            return await interaction.response.send_message(
                embed=error_embed(
                    "Insufficient Rank",
                    f"Only officers at **{req['emoji']} {req['label']}** may escalate this ticket.\n\n"
                    f"**Required:** {req['emoji']} {req['label']}\n"
                    f"**Your tier:** {my_label}"
                ),
                ephemeral=True,
            )
        await interaction.response.send_modal(EscalationModal())


# ── Escalation Modal ──────────────────────────────────────────────────────────
class EscalationModal(discord.ui.Modal, title="Escalate Ticket"):
    reason = discord.ui.TextInput(
        label="Reason for escalation",
        placeholder="Describe why this ticket needs higher-level attention…",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await TicketSystem.escalate_ticket(interaction, reason=self.reason.value)


# ── Confirm Close View ────────────────────────────────────────────────────────
class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="✅ Confirm Close", style=discord.ButtonStyle.danger, custom_id="ticket:confirm_close")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        tickets = load_data("tickets")
        ch_id   = str(interaction.channel.id)
        ticket  = tickets.get(ch_id)
        cfg     = get_config()

        log_ch   = interaction.guild.get_channel(cfg["channels"].get("ticket_logs", 0))
        trans_ch = interaction.guild.get_channel(
            cfg["channels"].get("transcript_channel", 0) or cfg["ticket"].get("transcript_channel", 0)
        )

        transcript_text = await TicketSystem.build_transcript(interaction.channel, ticket)

        if trans_ch:
            esc_level = ticket.get("escalation_level", 1) if ticket else 1
            tier_label = ESCALATION_TIERS[esc_level - 1]["label"]
            buf = io.BytesIO(transcript_text.encode())
            await trans_ch.send(
                embed=info_embed(
                    "Ticket Closed",
                    f"Ticket `{interaction.channel.name}` closed by {interaction.user.mention}\n"
                    f"Final tier: **{ESCALATION_TIERS[esc_level-1]['emoji']} {tier_label}**"
                ),
                file=discord.File(buf, filename=f"transcript-{interaction.channel.name}.txt"),
            )

        if log_ch:
            esc_level = ticket.get("escalation_level", 1) if ticket else 1
            log_embed = discord.Embed(title="🎟️ Ticket Closed", color=RED, timestamp=datetime.utcnow())
            log_embed.add_field(name="Channel",    value=interaction.channel.name,                    inline=True)
            log_embed.add_field(name="Closed By",  value=str(interaction.user),                        inline=True)
            log_embed.add_field(name="Final Tier", value=ESCALATION_TIERS[esc_level - 1]["label"],     inline=True)
            await log_ch.send(embed=log_embed)

        if ticket:
            tickets.pop(ch_id, None)
            save_data("tickets", tickets)

        await interaction.response.send_message(embed=success_embed("Closing ticket in 3 seconds…"))
        await asyncio.sleep(3)
        await interaction.channel.delete()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary, custom_id="ticket:cancel_close")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=info_embed("Cancelled", "Ticket close cancelled."), ephemeral=True)
        self.stop()


# ── Category Select ───────────────────────────────────────────────────────────
class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="General Support", emoji="💬", value="general", description="General questions and support"),
            discord.SelectOption(label="Report a User",   emoji="🚨", value="report",  description="Report a rule-breaking user"),
            discord.SelectOption(label="Ban Appeal",      emoji="⚖️", value="appeal",  description="Appeal a ban or punishment"),
            discord.SelectOption(label="Other",           emoji="❓", value="other",    description="Anything else"),
        ]
        super().__init__(placeholder="Select a category…", options=options, custom_id="ticket:category")

    async def callback(self, interaction: discord.Interaction):
        await TicketSystem.create_ticket(interaction, category=self.values[0])


class CategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(CategorySelect())


# ── Core Ticket Logic ─────────────────────────────────────────────────────────
class TicketSystem:

    @staticmethod
    async def create_ticket(interaction: discord.Interaction, category: str = "general"):
        cfg     = get_config()
        tickets = load_data("tickets")
        uid     = str(interaction.user.id)

        user_tickets = [t for t in tickets.values() if str(t.get("opener_id")) == uid and t.get("status") == "open"]
        max_open = cfg["ticket"].get("max_open_per_user", 2)
        if len(user_tickets) >= max_open:
            msg = error_embed("Limit Reached", f"You already have **{len(user_tickets)}** open tickets (max: {max_open}).")
            return (await interaction.followup.send(embed=msg, ephemeral=True)
                    if interaction.response.is_done()
                    else await interaction.response.send_message(embed=msg, ephemeral=True))

        guild      = interaction.guild
        cat_id     = cfg["channels"].get("ticket_category", 0)
        cat_obj    = guild.get_channel(cat_id) if cat_id else None
        ticket_num = len(tickets) + 1
        ch_name    = f"ticket-{interaction.user.name}-{ticket_num}".lower().replace(" ", "-")[:100]

        # Build overwrites — grant access to all roles configured for Tier 1 and above
        tier1_ids = all_tier_role_ids_up_to(1)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user:   discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True, read_message_history=True
            ),
        }
        ping_role = None
        for role_id in tier1_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
                if ping_role is None:
                    ping_role = role

        try:
            channel = await guild.create_text_channel(
                name=ch_name, category=cat_obj, overwrites=overwrites,
                topic=f"Ticket #{ticket_num} | {interaction.user} | {category.title()} | 🟢 Level 1 — Superintendent+"
            )
        except discord.Forbidden:
            msg = error_embed("Permission Error", "I don't have permission to create channels.")
            return (await interaction.followup.send(embed=msg, ephemeral=True)
                    if interaction.response.is_done()
                    else await interaction.response.send_message(embed=msg, ephemeral=True))

        tickets[str(channel.id)] = {
            "opener_id":        interaction.user.id,
            "opener_name":      str(interaction.user),
            "category":         category,
            "status":           "open",
            "created_at":       datetime.utcnow().isoformat(),
            "ticket_num":       ticket_num,
            "escalation_level": 1,
            "escalation_log":   [],
        }
        save_data("tickets", tickets)

        embed = discord.Embed(
            title=f"🎟️ Ticket #{ticket_num}",
            description=(
                f"Welcome {interaction.user.mention}!\n\n"
                f"**Category:** {category.title()}\n"
                f"**Assigned to:** 🟢 Tier 1 — Superintendent & above\n\n"
                f"Please describe your issue in detail. A qualified officer will assist you shortly.\n"
                f"Use **⬆️ Escalate** if you need senior command attention."
            ),
            color=CYAN,
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text=f"Opened by {interaction.user} | Tier 1 — Superintendent+")
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        await channel.send(
            content=f"{interaction.user.mention}" + (f" {ping_role.mention}" if ping_role else ""),
            embed=embed,
            view=TicketControlView(),
        )

        success = success_embed("Ticket Opened!", f"Your ticket has been created: {channel.mention}")
        if interaction.response.is_done():
            await interaction.followup.send(embed=success, ephemeral=True)
        else:
            await interaction.response.send_message(embed=success, ephemeral=True)

    @staticmethod
    async def escalate_ticket(interaction: discord.Interaction, reason: str):
        tickets = load_data("tickets")
        ch_id   = str(interaction.channel.id)
        ticket  = tickets.get(ch_id)
        if not ticket:
            return await interaction.response.send_message(embed=error_embed("Not a Ticket"), ephemeral=True)

        current_level = ticket.get("escalation_level", 1)
        if current_level >= len(ESCALATION_TIERS):
            return await interaction.response.send_message(
                embed=error_embed("Already at Final Escalation",
                                  f"This ticket is already at **{ESCALATION_TIERS[-1]['label']}**."),
                ephemeral=True,
            )

        if not can_handle_ticket(interaction.user, current_level):
            req = ESCALATION_TIERS[current_level - 1]
            return await interaction.response.send_message(
                embed=error_embed("Insufficient Rank",
                                  f"Only officers at **{req['description']}** may escalate this ticket."),
                ephemeral=True,
            )

        new_level = current_level + 1
        new_tier  = ESCALATION_TIERS[new_level - 1]
        prev_tier = ESCALATION_TIERS[current_level - 1]
        guild     = interaction.guild
        cfg       = get_config()

        # Grant channel access to all roles configured for the new tier and above
        new_ids  = all_tier_role_ids_up_to(new_level)
        ping_role = None
        for role_id in new_ids:
            role = guild.get_role(role_id)
            if role:
                await interaction.channel.set_permissions(role, view_channel=True, send_messages=True)
                if ping_role is None:
                    ping_role = role

        ticket["escalation_level"] = new_level
        ticket["escalation_log"].append({
            "from_level": current_level,
            "to_level":   new_level,
            "by":         str(interaction.user),
            "by_id":      interaction.user.id,
            "reason":     reason,
            "time":       datetime.utcnow().isoformat(),
        })
        save_data("tickets", tickets)

        await interaction.channel.edit(
            topic=f"Ticket #{ticket['ticket_num']} | {ticket['opener_name']} | "
                  f"{ticket['category'].title()} | {new_tier['emoji']} Level {new_level} — {new_tier['label']}"
        )

        esc_embed = discord.Embed(
            title=f"{new_tier['emoji']} Ticket Escalated — Level {new_level}",
            description=(
                f"**Escalated by:** {interaction.user.mention}\n"
                f"**From:** {prev_tier['emoji']} {prev_tier['label']}\n"
                f"**To:** {new_tier['emoji']} {new_tier['label']}\n\n"
                f"**Reason:**\n> {reason}\n\n"
                f"*This ticket now requires attention from an officer at "
                f"**{new_tier['description']}**.*"
            ),
            color=ESCALATION_COLORS.get(new_level, ORANGE),
            timestamp=datetime.utcnow(),
        )
        esc_embed.set_footer(text=f"Ticket #{ticket['ticket_num']} | Escalation {new_level}/{len(ESCALATION_TIERS)}")

        ping_content = f"🚨 {ping_role.mention} — this ticket requires your attention!" if ping_role else "🚨 This ticket has been escalated!"
        await interaction.channel.send(content=ping_content, embed=esc_embed)

        log_ch_id = cfg["channels"].get("ticket_logs", 0)
        if log_ch_id:
            log_ch = guild.get_channel(log_ch_id)
            if log_ch:
                log_embed = discord.Embed(title="⬆️ Ticket Escalated",
                                          color=ESCALATION_COLORS.get(new_level, ORANGE),
                                          timestamp=datetime.utcnow())
                log_embed.add_field(name="Ticket",       value=interaction.channel.mention,                    inline=True)
                log_embed.add_field(name="Escalated By", value=f"{interaction.user} ({interaction.user.id})",  inline=True)
                log_embed.add_field(name="Transition",   value=f"{prev_tier['label']} → {new_tier['label']}", inline=True)
                log_embed.add_field(name="Reason",       value=reason,                                         inline=False)
                await log_ch.send(embed=log_embed)

        await interaction.response.send_message(
            embed=success_embed("Ticket Escalated",
                                f"Escalated to **{new_tier['emoji']} {new_tier['label']}**.\n"
                                f"Qualified officers have been notified."),
            ephemeral=True,
        )

    @staticmethod
    async def close_ticket(interaction: discord.Interaction):
        tickets = load_data("tickets")
        if str(interaction.channel.id) not in tickets:
            return await interaction.response.send_message(
                embed=error_embed("Not a Ticket", "This command can only be used inside a ticket channel."),
                ephemeral=True,
            )
        await interaction.response.send_message(
            embed=warn_embed("Close Ticket?", "Are you sure?\nA full transcript will be saved automatically."),
            view=ConfirmCloseView(),
        )

    @staticmethod
    async def build_transcript(channel: discord.TextChannel, ticket: dict) -> str:
        esc_level = ticket.get("escalation_level", 1) if ticket else 1
        esc_log   = ticket.get("escalation_log", [])  if ticket else []
        lines = [
            "═══ TICKET TRANSCRIPT ═══",
            f"Channel      : #{channel.name}",
            f"Opened By    : {ticket.get('opener_name', 'Unknown') if ticket else 'Unknown'}",
            f"Category     : {ticket.get('category', 'N/A') if ticket else 'N/A'}",
            f"Created      : {ticket.get('created_at', 'N/A') if ticket else 'N/A'}",
            f"Final Tier   : {ESCALATION_TIERS[esc_level-1]['label']} (Level {esc_level})",
            f"Exported     : {datetime.utcnow().isoformat()}",
        ]
        if esc_log:
            lines.append("\n── Escalation History ──")
            for e in esc_log:
                ft = ESCALATION_TIERS[e["from_level"] - 1]["label"]
                tt = ESCALATION_TIERS[e["to_level"]   - 1]["label"]
                lines.append(f"  [{e['time'][:19]}] {e['by']}: {ft} → {tt} | {e['reason']}")
        lines.append("═════════════════════════\n")
        async for msg in channel.history(limit=500, oldest_first=True):
            ts   = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            body = msg.clean_content or "[embed/attachment]"
            lines.append(f"[{ts}] {msg.author}: {body}")
        return "\n".join(lines)

    @staticmethod
    async def send_transcript(interaction: discord.Interaction):
        tickets = load_data("tickets")
        ticket  = tickets.get(str(interaction.channel.id))
        await interaction.response.defer(ephemeral=True)
        text = await TicketSystem.build_transcript(interaction.channel, ticket)
        buf  = io.BytesIO(text.encode())
        await interaction.followup.send(
            embed=info_embed("Transcript", "Here is the current transcript:"),
            file=discord.File(buf, filename=f"transcript-{interaction.channel.name}.txt"),
            ephemeral=True,
        )


# ── Tickets Cog ───────────────────────────────────────────────────────────────
class Tickets(commands.Cog):
    """🎟️ Ticket System"""

    def __init__(self, bot):
        self.bot = bot
        bot.add_view(TicketPanelView())
        bot.add_view(TicketControlView())

    ticket = app_commands.Group(name="ticket", description="Ticket system commands.")
    tier_group = app_commands.Group(name="tier", description="Configure role IDs for each ticket tier.", parent=ticket)

    # ── /ticket setup ─────────────────────────────────────────────────────────
    @ticket.command(name="setup", description="Post the ticket panel in this channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎟️ Support Tickets",
            description=(
                "Need help? Click the button below to open a support ticket.\n\n"
                "**Please include:**\n"
                "• A clear description of your issue\n"
                "• Any relevant screenshots or details\n\n"
                "*Misuse of the ticket system will result in punishment.*"
            ),
            color=CYAN,
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text=interaction.guild.name)
        await interaction.channel.send(embed=embed, view=TicketPanelView())
        await interaction.response.send_message(embed=success_embed("Panel Created!"), ephemeral=True)

    # ── /ticket open ──────────────────────────────────────────────────────────
    @ticket.command(name="open", description="Open a support ticket.")
    async def open(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=info_embed("Open a Ticket", "Please select a category for your ticket:"),
            view=CategoryView(),
            ephemeral=True,
        )

    # ── /ticket close ─────────────────────────────────────────────────────────
    @ticket.command(name="close", description="Close the current ticket.")
    async def close(self, interaction: discord.Interaction):
        await TicketSystem.close_ticket(interaction)

    # ── /ticket escalate ──────────────────────────────────────────────────────
    @ticket.command(name="escalate", description="Escalate this ticket to a higher command tier.")
    @app_commands.describe(reason="Why does this ticket need escalation?")
    async def escalate(self, interaction: discord.Interaction, reason: str):
        tickets = load_data("tickets")
        ticket  = tickets.get(str(interaction.channel.id))
        if not ticket:
            return await interaction.response.send_message(embed=error_embed("Not a Ticket"), ephemeral=True)
        current_level = ticket.get("escalation_level", 1)
        if not can_handle_ticket(interaction.user, current_level):
            req = ESCALATION_TIERS[current_level - 1]
            return await interaction.response.send_message(
                embed=error_embed("Insufficient Rank",
                                  f"Only officers at **{req['description']}** may escalate this ticket."),
                ephemeral=True,
            )
        await TicketSystem.escalate_ticket(interaction, reason=reason)

    # ── /ticket escalation ────────────────────────────────────────────────────
    @ticket.command(name="escalation", description="View the escalation history of this ticket.")
    async def escalation(self, interaction: discord.Interaction):
        tickets = load_data("tickets")
        ticket  = tickets.get(str(interaction.channel.id))
        if not ticket:
            return await interaction.response.send_message(embed=error_embed("Not a Ticket"), ephemeral=True)

        level   = ticket.get("escalation_level", 1)
        tier    = ESCALATION_TIERS[level - 1]
        esc_log = ticket.get("escalation_log", [])

        embed = discord.Embed(
            title=f"📋 Escalation History — Ticket #{ticket.get('ticket_num', '?')}",
            color=ESCALATION_COLORS.get(level, CYAN),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(
            name="Current Tier",
            value=f"{tier['emoji']} Level {level} — **{tier['label']}**\n_{tier['description']}_",
            inline=False,
        )
        if not esc_log:
            embed.add_field(name="History", value="No escalations have occurred yet.", inline=False)
        else:
            for i, e in enumerate(esc_log, 1):
                ft = ESCALATION_TIERS[e["from_level"] - 1]
                tt = ESCALATION_TIERS[e["to_level"]   - 1]
                embed.add_field(
                    name=f"Escalation #{i} — {e['time'][:10]}",
                    value=f"{ft['emoji']} {ft['label']} → {tt['emoji']} {tt['label']}\n**By:** {e['by']}\n**Reason:** {e['reason']}",
                    inline=False,
                )
        if level < len(ESCALATION_TIERS):
            nt = ESCALATION_TIERS[level]
            embed.add_field(name="Next Escalation", value=f"{nt['emoji']} Level {nt['level']} — **{nt['label']}**", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /ticket add ───────────────────────────────────────────────────────────
    @ticket.command(name="add", description="Add a user to the current ticket.")
    @app_commands.describe(member="Member to add")
    async def add(self, interaction: discord.Interaction, member: discord.Member):
        if str(interaction.channel.id) not in load_data("tickets"):
            return await interaction.response.send_message(embed=error_embed("Not a Ticket"), ephemeral=True)
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True)
        await interaction.response.send_message(embed=success_embed("User Added", f"{member.mention} added to this ticket."))

    # ── /ticket remove ────────────────────────────────────────────────────────
    @ticket.command(name="remove", description="Remove a user from the current ticket.")
    @app_commands.describe(member="Member to remove")
    async def remove(self, interaction: discord.Interaction, member: discord.Member):
        if str(interaction.channel.id) not in load_data("tickets"):
            return await interaction.response.send_message(embed=error_embed("Not a Ticket"), ephemeral=True)
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(embed=success_embed("User Removed", f"{member.mention} removed from this ticket."))

    # ── /ticket list ──────────────────────────────────────────────────────────
    @ticket.command(name="list", description="List all open tickets.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def list(self, interaction: discord.Interaction):
        tickets      = load_data("tickets")
        open_tickets = [(cid, t) for cid, t in tickets.items() if t.get("status") == "open"]
        embed = info_embed("Open Tickets", f"**{len(open_tickets)}** open ticket(s)")
        for cid, t in open_tickets[:15]:
            ch    = interaction.guild.get_channel(int(cid))
            level = t.get("escalation_level", 1)
            tier  = ESCALATION_TIERS[level - 1]
            embed.add_field(
                name=f"Ticket #{t.get('ticket_num', '?')} {tier['emoji']}",
                value=(
                    f"{ch.mention if ch else f'#{cid}'}\n"
                    f"Opened by **{t.get('opener_name', '?')}** | {t.get('category', '?').title()}\n"
                    f"Tier: **{tier['label']}**"
                ),
                inline=True,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ══════════════════════════════════════════════════════════════════════════
    # /ticket tier  — role ID management for each escalation tier
    # ══════════════════════════════════════════════════════════════════════════

    # ── /ticket tier view ─────────────────────────────────────────────────────
    @tier_group.command(name="view", description="Show all roles configured for each ticket tier.")
    @app_commands.checks.has_permissions(administrator=True)
    async def tier_view(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏛️ Ticket Tier Role Configuration",
            description=(
                "These are the Discord roles assigned to each escalation tier.\n"
                "Members with **any** listed role can handle tickets at that tier level.\n"
                "Higher-tier roles also qualify for lower tiers automatically."
            ),
            color=BLUE,
            timestamp=datetime.utcnow(),
        )
        for tier in ESCALATION_TIERS:
            ids   = get_tier_role_ids(tier["level"])
            if ids:
                roles_str = "\n".join(
                    f"• {interaction.guild.get_role(rid).mention if interaction.guild.get_role(rid) else f'Unknown role ({rid})'}"
                    for rid in ids
                )
            else:
                roles_str = "*No roles configured yet.*\nUse `/ticket tier addrole` to add some."
            embed.add_field(
                name=f"{tier['emoji']} Level {tier['level']} — {tier['label']}",
                value=f"_{tier['description']}_\n{roles_str}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /ticket tier addrole ──────────────────────────────────────────────────
    @tier_group.command(name="addrole", description="Add a role to a ticket tier.")
    @app_commands.describe(
        level="Tier level (1 = Superintendent+, 2 = DAC+, 3 = Deputy Commissioner+)",
        role="The Discord role to add to this tier",
    )
    @app_commands.choices(level=[
        app_commands.Choice(name="Level 1 — Superintendent+",               value=1),
        app_commands.Choice(name="Level 2 — Deputy Assistant Commissioner+", value=2),
        app_commands.Choice(name="Level 3 — Deputy Commissioner+",           value=3),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def tier_addrole(self, interaction: discord.Interaction, level: int, role: discord.Role):
        ids = get_tier_role_ids(level)
        if role.id in ids:
            return await interaction.response.send_message(
                embed=warn_embed("Already Added", f"{role.mention} is already in **Tier {level}**."),
                ephemeral=True,
            )
        ids.append(role.id)
        set_tier_role_ids(level, ids)
        tier = ESCALATION_TIERS[level - 1]
        await interaction.response.send_message(
            embed=success_embed(
                "Role Added",
                f"{role.mention} added to **{tier['emoji']} Tier {level} — {tier['label']}**.\n"
                f"Members with this role can now handle and escalate Level {level} tickets."
            ),
            ephemeral=True,
        )

    # ── /ticket tier removerole ───────────────────────────────────────────────
    @tier_group.command(name="removerole", description="Remove a role from a ticket tier.")
    @app_commands.describe(
        level="Tier level to remove the role from",
        role="The Discord role to remove",
    )
    @app_commands.choices(level=[
        app_commands.Choice(name="Level 1 — Superintendent+",               value=1),
        app_commands.Choice(name="Level 2 — Deputy Assistant Commissioner+", value=2),
        app_commands.Choice(name="Level 3 — Deputy Commissioner+",           value=3),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def tier_removerole(self, interaction: discord.Interaction, level: int, role: discord.Role):
        ids = get_tier_role_ids(level)
        if role.id not in ids:
            return await interaction.response.send_message(
                embed=error_embed("Not Found", f"{role.mention} is not in **Tier {level}**."),
                ephemeral=True,
            )
        ids.remove(role.id)
        set_tier_role_ids(level, ids)
        tier = ESCALATION_TIERS[level - 1]
        await interaction.response.send_message(
            embed=success_embed(
                "Role Removed",
                f"{role.mention} removed from **{tier['emoji']} Tier {level} — {tier['label']}**."
            ),
            ephemeral=True,
        )

    # ── /ticket tier clearroles ───────────────────────────────────────────────
    @tier_group.command(name="clearroles", description="Remove ALL roles from a ticket tier.")
    @app_commands.describe(level="Tier level to clear")
    @app_commands.choices(level=[
        app_commands.Choice(name="Level 1 — Superintendent+",               value=1),
        app_commands.Choice(name="Level 2 — Deputy Assistant Commissioner+", value=2),
        app_commands.Choice(name="Level 3 — Deputy Commissioner+",           value=3),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def tier_clearroles(self, interaction: discord.Interaction, level: int):
        set_tier_role_ids(level, [])
        tier = ESCALATION_TIERS[level - 1]
        await interaction.response.send_message(
            embed=success_embed("Roles Cleared", f"All roles removed from **{tier['emoji']} Tier {level} — {tier['label']}**."),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Tickets(bot))
