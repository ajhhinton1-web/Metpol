# 🤖 Discord Admin Bot — Replit Edition

A full-featured Discord admin bot with **Metropolitan Police rank-based ticket escalation**, Roblox event hosting, and Roblox group ranking. Built with discord.py 2.x slash commands.

---

## 🚀 Replit Setup (5 minutes)

### Step 1 — Import into Replit

1. Go to [replit.com](https://replit.com) → **Create Repl**
2. Choose **Import from GitHub** (or upload the zip)
3. Select **Python** as the language

---

### Step 2 — Set Secrets

> ⚠️ **Never** put your token or cookie directly in `config.json`. Use Replit Secrets instead.

Go to **Tools → Secrets** in the left sidebar and add these four secrets:

| Key | Value |
|-----|-------|
| `DISCORD_TOKEN` | Your Discord bot token |
| `GUILD_ID` | Your Discord server ID |
| `ROBLOX_COOKIE` | Your `.ROBLOSECURITY` cookie |
| `ROBLOX_GROUP_ID` | Your Roblox group ID |

**How to get each value:**

- **DISCORD_TOKEN** — [discord.com/developers](https://discord.com/developers/applications) → your app → Bot → Reset Token
- **GUILD_ID** — In Discord: enable Developer Mode (User Settings → Advanced) → right-click your server → Copy Server ID
- **ROBLOX_COOKIE** — Log into Roblox in browser → F12 → Application tab → Cookies → copy `.ROBLOSECURITY` value
- **ROBLOX_GROUP_ID** — Your group's URL: `roblox.com/groups/XXXXXXX/...` — the number is the ID

---

### Step 3 — Edit config.json

Open `config.json` and fill in your **channel IDs** and **role names**:

```json
"roles": {
  "admin": "Admin",          ← exact name of your Admin role
  "moderator": "Moderator",  ← exact name of your Moderator role
  ...
},
"channels": {
  "logs": 123456789,              ← right-click channel → Copy Channel ID
  "ticket_category": 123456789,   ← this should be a CATEGORY, not a text channel
  "ticket_logs": 123456789,
  "transcript_channel": 123456789,
  "event_announcements": 123456789,
  "ranking_logs": 123456789,
  "welcome": 123456789
}
```

Leave any channel as `0` to disable that feature.

---

### Step 4 — Create Met Police Roles in Discord

Go to **Server Settings → Roles** and create roles with these **exact names** for the ticket escalation system:

**Tier 1 (Superintendent+) — handles new tickets:**
- Superintendent, Chief Superintendent, Commander, Detective Chief Superintendent

**Tier 2 (Deputy Assistant Commissioner+) — first escalation:**
- Deputy Assistant Commissioner, Assistant Commissioner

**Tier 3 (Deputy Commissioner+) — final escalation:**
- Deputy Commissioner, Commissioner

You only need to create the ranks your server actually uses. At least one role per tier is required for escalation to work properly.

---

### Step 5 — Invite the Bot

In the Discord Developer Portal:
1. Go to **OAuth2 → URL Generator**
2. Tick `bot` and `applications.commands`
3. Tick **Administrator** under Bot Permissions
4. Copy and open the URL, invite the bot to your server

---

### Step 6 — Run

Hit the **▶ Run** button in Replit. You'll see in the console:

```
Keep-alive server running on port 8080
Loaded: cogs.admin
Loaded: cogs.tickets
...
Slash commands synced to guild (instant).
Logged in as YourBot#1234
```

---

### Step 7 — Set up the ticket panel

In your desired channel, run:
```
/ticket setup
```

This posts the persistent **🎟️ Open a Ticket** button.

---

## 💤 Keeping the Bot Online 24/7 (Free Tier)

Replit free tier sleeps after ~1 hour of inactivity. The bot has a built-in HTTP server on port **8080** that responds to pings. Use **[UptimeRobot](https://uptimerobot.com)** (free) to ping it every 5 minutes:

1. Sign up at [uptimerobot.com](https://uptimerobot.com)
2. Add a new monitor → **HTTP(S)** type
3. URL: `https://your-repl-name.your-username.repl.co`
4. Interval: **5 minutes**

That's it — your bot stays online permanently on the free tier.

---

## 📋 All Commands

| Group | Command | Description | Required Rank |
|-------|---------|-------------|---------------|
| — | `/help` | Show all commands | Anyone |
| — | `/serverinfo` | Server statistics | Anyone |
| — | `/userinfo` | User profile | Anyone |
| — | `/ban` | Ban a member | Admin/Mod |
| — | `/unban` | Unban by user ID | Admin/Mod |
| — | `/kick` | Kick a member | Admin/Mod |
| — | `/mute` | Timeout a member | Admin/Mod |
| — | `/unmute` | Remove timeout | Admin/Mod |
| — | `/warn` | Issue a warning | Admin/Mod |
| — | `/warnings` | View warnings | Admin/Mod |
| — | `/clearwarnings` | Clear warnings | Admin/Mod |
| — | `/purge` | Bulk delete messages | Admin/Mod |
| — | `/slowmode` | Set channel slowmode | Admin/Mod |
| — | `/lock` | Lock a channel | Admin/Mod |
| — | `/unlock` | Unlock a channel | Admin/Mod |
| — | `/addrole` | Add role to member | Admin/Mod |
| — | `/removerole` | Remove role | Admin/Mod |
| — | `/nickname` | Change nickname | Admin/Mod |
| — | `/announce` | Send embed announcement | Admin/Mod |
| — | `/poll` | Create yes/no poll | Manage Messages |
| **ticket** | `/ticket setup` | Post ticket panel | Administrator |
| **ticket** | `/ticket open` | Open a ticket | Anyone |
| **ticket** | `/ticket close` | Close ticket | Anyone in ticket |
| **ticket** | `/ticket escalate` | Escalate ticket | Superintendent+ |
| **ticket** | `/ticket escalation` | View escalation history | Anyone in ticket |
| **ticket** | `/ticket add` | Add user to ticket | Staff |
| **ticket** | `/ticket remove` | Remove user | Staff |
| **ticket** | `/ticket list` | List open tickets | Manage Channels |
| **ticket** | `/ticket ranks` | Show Met Police tier requirements | Anyone |
| **event** | `/event create` | Schedule a Roblox event | Event Host |
| **event** | `/event start` | Announce event live | Event Host |
| **event** | `/event cancel` | Cancel an event | Event Host |
| **event** | `/event list` | List upcoming events | Anyone |
| **event** | `/event info` | Details on one event | Anyone |
| **rank** | `/rank get` | Get a user's group rank | Admin/Mod |
| **rank** | `/rank set` | Set rank by ID | Admin/Mod |
| **rank** | `/rank promote` | Promote one rank | Admin/Mod |
| **rank** | `/rank demote` | Demote one rank | Admin/Mod |
| **rank** | `/rank exile` | Remove from group | Administrator |
| **rank** | `/rank list` | List all group ranks | Admin/Mod |
| **rank** | `/rank verify` | Link Discord ↔ Roblox | Anyone |
| **rank** | `/rank whois` | Look up linked account | Anyone |
| **automod** | `/automod antiinvite` | Toggle invite link removal | Administrator |
| **automod** | `/automod antispam` | Toggle spam detection | Administrator |
| **automod** | `/automod status` | View automod settings | Anyone |

---

## 🎟️ Ticket Escalation Tiers

| Level | Tier | Qualifying Ranks |
|-------|------|-----------------|
| 🟢 1 | Superintendent+ | Superintendent, Chief Superintendent, Commander, Det. Chief Supt, DAC, AC, DC, Commissioner |
| 🟡 2 | Deputy Assistant Commissioner+ | DAC, Assistant Commissioner, Deputy Commissioner, Commissioner |
| 🔴 3 | Deputy Commissioner+ | Deputy Commissioner, Commissioner |

---

## 📁 File Structure

```
discord-bot/
├── bot.py                  # Entry point + keep-alive server
├── config.json             # Non-sensitive config (channel IDs, role names)
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Replit dependency config
├── .replit                 # Replit run config
├── replit.nix              # Nix environment
├── .gitignore
├── cogs/
│   ├── admin.py            # Admin & moderation slash commands
│   ├── tickets.py          # Met Police rank-based ticket system
│   ├── roblox_events.py    # Roblox event hosting + RSVP
│   ├── roblox_ranking.py   # Roblox group ranking API
│   └── moderation.py       # Auto-mod + join/leave/edit logging
├── utils/
│   └── helpers.py          # Shared embeds, data store, config loader
└── data/                   # Auto-created JSON storage (gitignored)
    ├── warnings.json
    ├── tickets.json
    ├── events.json
    ├── roblox_links.json
    └── automod_settings.json
```
