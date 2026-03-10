import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import asyncio, uuid

from utils.helpers import (success_embed, error_embed, info_embed, warn_embed,
                           load_data, save_data, get_config, GREEN, RED, BLUE, PURPLE, ORANGE)


GAME_TYPES = ["Training", "Tryout", "Raid", "Alliance Event", "Patrol", "Meeting", "Competition", "Other"]


def is_host():
    async def predicate(interaction: discord.Interaction) -> bool:
        cfg = get_config()
        host_role  = cfg["roles"].get("roblox_host", "Event Host")
        admin_role = cfg["roles"].get("admin", "Admin")
        if interaction.user.guild_permissions.administrator:
            return True
        if any(r.name in (host_role, admin_role) for r in interaction.user.roles):
            return True
        raise app_commands.MissingPermissions(["Event Host role"])
    return app_commands.check(predicate)


# ── RSVP View ─────────────────────────────────────────────────────────────────
class RSVPView(discord.ui.View):
    def __init__(self, event_id: str):
        super().__init__(timeout=None)
        self.event_id = event_id
        self.custom_id_yes = f"rsvp:yes:{event_id}"
        self.custom_id_no  = f"rsvp:no:{event_id}"

    @discord.ui.button(label="✅ Attending", style=discord.ButtonStyle.success, custom_id="rsvp:yes:placeholder")
    async def attending(self, interaction: discord.Interaction, button: discord.ui.Button):
        events = load_data("events")
        eid    = None
        for k, v in events.items():
            if k == self.event_id or str(interaction.message.id) in str(v.get("message_id", "")):
                eid = k
                break
        # Try finding by message id
        for k, v in events.items():
            if str(v.get("message_id")) == str(interaction.message.id):
                eid = k
                break
        if not eid:
            # Fallback: use event_id stored on view
            eid = self.event_id
        event = events.get(eid)
        if not event:
            return await interaction.response.send_message(embed=error_embed("Event not found."), ephemeral=True)
        uid   = str(interaction.user.id)
        event.setdefault("attendees", [])
        event.setdefault("declined", [])
        if uid in event["attendees"]:
            return await interaction.response.send_message(embed=info_embed("Already RSVP'd", "You're already marked as attending!"), ephemeral=True)
        event["attendees"].append(uid)
        if uid in event["declined"]:
            event["declined"].remove(uid)
        save_data("events", events)
        await interaction.response.send_message(embed=success_embed("RSVP Confirmed!", f"You're attending **{event['title']}**."), ephemeral=True)

    @discord.ui.button(label="❌ Not Attending", style=discord.ButtonStyle.danger, custom_id="rsvp:no:placeholder")
    async def not_attending(self, interaction: discord.Interaction, button: discord.ui.Button):
        events = load_data("events")
        eid    = None
        for k, v in events.items():
            if str(v.get("message_id")) == str(interaction.message.id):
                eid = k
                break
        if not eid:
            eid = self.event_id
        event = events.get(eid)
        if not event:
            return await interaction.response.send_message(embed=error_embed("Event not found."), ephemeral=True)
        uid = str(interaction.user.id)
        event.setdefault("attendees", [])
        event.setdefault("declined",  [])
        if uid in event["declined"]:
            return await interaction.response.send_message(embed=info_embed("Already Declined", "You've already declined this event."), ephemeral=True)
        event["declined"].append(uid)
        if uid in event["attendees"]:
            event["attendees"].remove(uid)
        save_data("events", events)
        await interaction.response.send_message(embed=info_embed("RSVP Updated", f"You've declined **{event['title']}**."), ephemeral=True)


# ── Cog ───────────────────────────────────────────────────────────────────────
class RobloxEvents(commands.Cog):
    """🎮 Roblox Event Hosting"""

    def __init__(self, bot):
        self.bot    = bot
        self.config = get_config()
        self.event_reminder_loop.start()

    def cog_unload(self):
        self.event_reminder_loop.cancel()

    event = app_commands.Group(name="event", description="Roblox event management commands.")

    # ── /event create ─────────────────────────────────────────────────────────
    @event.command(name="create", description="Schedule a new Roblox event.")
    @app_commands.describe(
        title="Event name",
        game_type="Type of event",
        date="Date of event (YYYY-MM-DD)",
        time="Time of event (HH:MM, 24hr UTC)",
        description="Event description",
        game_link="Roblox game link",
        image_url="Optional banner image URL"
    )
    @app_commands.choices(game_type=[app_commands.Choice(name=g, value=g) for g in GAME_TYPES])
    @is_host()
    async def create(self, interaction: discord.Interaction,
                     title: str, game_type: str, date: str, time: str,
                     description: str = "", game_link: str = "", image_url: str = ""):
        await interaction.response.defer(ephemeral=True)
        try:
            event_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        except ValueError:
            return await interaction.followup.send(embed=error_embed("Invalid Date/Time", "Use format: `YYYY-MM-DD` and `HH:MM`"), ephemeral=True)

        if event_dt < datetime.utcnow():
            return await interaction.followup.send(embed=error_embed("Past Date", "You can't schedule an event in the past."), ephemeral=True)

        event_id = str(uuid.uuid4())[:8]
        ann_ch_id = self.config["channels"].get("event_announcements", 0)
        ann_ch = interaction.guild.get_channel(ann_ch_id) if ann_ch_id else interaction.channel

        embed = discord.Embed(
            title=f"📅 {title}",
            description=description or "Come join us for an exciting event!",
            color=PURPLE,
            timestamp=event_dt
        )
        embed.add_field(name="📌 Type",      value=game_type,                         inline=True)
        embed.add_field(name="🕐 Date/Time", value=f"<t:{int(event_dt.timestamp())}:F>", inline=True)
        embed.add_field(name="👤 Host",      value=interaction.user.mention,           inline=True)
        if game_link:
            embed.add_field(name="🎮 Game Link", value=f"[Click to Join]({game_link})", inline=False)
        embed.add_field(name="✅ Attending", value="0 members", inline=True)
        embed.add_field(name="❌ Declined",  value="0 members", inline=True)
        embed.set_footer(text=f"Event ID: {event_id} | React to RSVP!")
        if image_url:
            embed.set_image(url=image_url)

        view = RSVPView(event_id)
        msg  = await ann_ch.send(embed=embed, view=view)

        events = load_data("events")
        events[event_id] = {
            "title":       title,
            "type":        game_type,
            "description": description,
            "date":        date,
            "time":        time,
            "timestamp":   event_dt.isoformat(),
            "host_id":     interaction.user.id,
            "host_name":   str(interaction.user),
            "game_link":   game_link,
            "image_url":   image_url,
            "guild_id":    interaction.guild.id,
            "channel_id":  ann_ch.id,
            "message_id":  msg.id,
            "attendees":   [],
            "declined":    [],
            "status":      "scheduled",
        }
        save_data("events", events)
        await interaction.followup.send(embed=success_embed("Event Scheduled!", f"**{title}** has been posted in {ann_ch.mention}\nEvent ID: `{event_id}`"), ephemeral=True)

    # ── /event start ──────────────────────────────────────────────────────────
    @event.command(name="start", description="Announce that an event has started.")
    @app_commands.describe(event_id="The Event ID to start")
    @is_host()
    async def start(self, interaction: discord.Interaction, event_id: str):
        await interaction.response.defer(ephemeral=True)
        events = load_data("events")
        ev = events.get(event_id)
        if not ev:
            return await interaction.followup.send(embed=error_embed("Not Found", f"No event with ID `{event_id}`."), ephemeral=True)

        ann_ch = interaction.guild.get_channel(self.config["channels"].get("event_announcements", 0)) or interaction.channel
        embed  = discord.Embed(
            title=f"🟢 Event Starting NOW — {ev['title']}",
            description=(
                f"**{ev['title']}** is **now live!**\n\n"
                f"🕐 Type: **{ev['type']}**\n"
                f"👤 Host: <@{ev['host_id']}>\n"
            ) + (f"🎮 [Join Game]({ev['game_link']})" if ev.get("game_link") else ""),
            color=GREEN,
            timestamp=datetime.utcnow()
        )
        if ev.get("image_url"):
            embed.set_image(url=ev["image_url"])
        attending = len(ev.get("attendees", []))
        embed.set_footer(text=f"{attending} member(s) attending | Event ID: {event_id}")

        # Ping attendees
        mentions = " ".join(f"<@{uid}>" for uid in ev.get("attendees", []))
        await ann_ch.send(content=f"🚨 **Event Starting!** {mentions}", embed=embed)

        ev["status"] = "started"
        save_data("events", events)
        await interaction.followup.send(embed=success_embed("Event Started!", f"**{ev['title']}** announcement sent."), ephemeral=True)

    # ── /event cancel ─────────────────────────────────────────────────────────
    @event.command(name="cancel", description="Cancel a scheduled event.")
    @app_commands.describe(event_id="The Event ID to cancel", reason="Reason for cancellation")
    @is_host()
    async def cancel(self, interaction: discord.Interaction, event_id: str, reason: str = "No reason provided"):
        await interaction.response.defer(ephemeral=True)
        events = load_data("events")
        ev = events.get(event_id)
        if not ev:
            return await interaction.followup.send(embed=error_embed("Not Found", f"No event with ID `{event_id}`."), ephemeral=True)

        ann_ch = interaction.guild.get_channel(ev.get("channel_id", 0)) or interaction.channel
        embed  = discord.Embed(
            title=f"🔴 Event Cancelled — {ev['title']}",
            description=f"**Reason:** {reason}\n\nApologies for any inconvenience.",
            color=RED,
            timestamp=datetime.utcnow()
        )
        mentions = " ".join(f"<@{uid}>" for uid in ev.get("attendees", []))
        await ann_ch.send(content=f"⚠️ **Event Cancelled** {mentions}", embed=embed)

        # Try to delete original event message
        try:
            orig_msg = await ann_ch.fetch_message(ev.get("message_id", 0))
            await orig_msg.delete()
        except Exception:
            pass

        events.pop(event_id, None)
        save_data("events", events)
        await interaction.followup.send(embed=success_embed("Event Cancelled", f"**{ev['title']}** has been cancelled."), ephemeral=True)

    # ── /event list ───────────────────────────────────────────────────────────
    @event.command(name="list", description="List all upcoming events.")
    async def list(self, interaction: discord.Interaction):
        events = load_data("events")
        scheduled = [(eid, ev) for eid, ev in events.items()
                     if ev.get("status") in ("scheduled", "started") and ev.get("guild_id") == interaction.guild.id]
        scheduled.sort(key=lambda x: x[1].get("timestamp", ""))

        embed = discord.Embed(title="📅 Upcoming Events", color=PURPLE, timestamp=datetime.utcnow())
        if not scheduled:
            embed.description = "No upcoming events scheduled."
        else:
            for eid, ev in scheduled[:10]:
                ts    = ev.get("timestamp", "")
                dt    = datetime.fromisoformat(ts) if ts else None
                time_str = f"<t:{int(dt.timestamp())}:R>" if dt else "Unknown"
                embed.add_field(
                    name=f"{'🟢' if ev['status'] == 'started' else '📅'} {ev['title']}",
                    value=(
                        f"Type: **{ev['type']}** | Host: <@{ev['host_id']}>\n"
                        f"When: {time_str} | ID: `{eid}`\n"
                        f"✅ {len(ev.get('attendees',[]))} attending"
                    ),
                    inline=False
                )
        await interaction.response.send_message(embed=embed)

    # ── /event info ───────────────────────────────────────────────────────────
    @event.command(name="info", description="Get details about a specific event.")
    @app_commands.describe(event_id="The Event ID")
    async def info(self, interaction: discord.Interaction, event_id: str):
        events = load_data("events")
        ev = events.get(event_id)
        if not ev:
            return await interaction.response.send_message(embed=error_embed("Not Found", f"No event with ID `{event_id}`."), ephemeral=True)

        ts  = ev.get("timestamp", "")
        dt  = datetime.fromisoformat(ts) if ts else None
        embed = discord.Embed(title=f"📅 {ev['title']}", color=PURPLE, timestamp=dt or datetime.utcnow())
        embed.add_field(name="Type",      value=ev.get("type", "N/A"),   inline=True)
        embed.add_field(name="Host",      value=f"<@{ev['host_id']}>",   inline=True)
        embed.add_field(name="Status",    value=ev.get("status", "?").title(), inline=True)
        if dt:
            embed.add_field(name="Date/Time", value=f"<t:{int(dt.timestamp())}:F>", inline=False)
        embed.add_field(name="Attending", value=str(len(ev.get("attendees", []))), inline=True)
        embed.add_field(name="Declined",  value=str(len(ev.get("declined", []))),  inline=True)
        if ev.get("game_link"):
            embed.add_field(name="Game Link", value=f"[Join]({ev['game_link']})", inline=False)
        if ev.get("image_url"):
            embed.set_image(url=ev["image_url"])
        embed.set_footer(text=f"Event ID: {event_id}")
        await interaction.response.send_message(embed=embed)

    # ── Reminder Loop ─────────────────────────────────────────────────────────
    @tasks.loop(minutes=5)
    async def event_reminder_loop(self):
        events = load_data("events")
        now    = datetime.utcnow()
        for eid, ev in list(events.items()):
            if ev.get("status") != "scheduled":
                continue
            ts = ev.get("timestamp")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                continue
            diff = (dt - now).total_seconds()
            if 0 < diff <= 900 and not ev.get("reminded_15"):  # 15 min reminder
                guild = self.bot.get_guild(ev.get("guild_id", 0))
                if guild:
                    ann_ch = guild.get_channel(self.config["channels"].get("event_announcements", 0))
                    if ann_ch:
                        mentions = " ".join(f"<@{uid}>" for uid in ev.get("attendees", []))
                        await ann_ch.send(
                            content=f"⏰ **{ev['title']}** starts in **15 minutes!** {mentions}",
                            embed=info_embed("Event Reminder", f"**{ev['title']}** starts <t:{int(dt.timestamp())}:R>!")
                        )
                ev["reminded_15"] = True
                events[eid] = ev
        save_data("events", events)

    @event_reminder_loop.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(RobloxEvents(bot))
