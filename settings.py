# =============================================================================
#  ⚙️  BOT SETTINGS — Edit everything here, then repack/restart
# =============================================================================
#
#  SENSITIVE VALUES (token, Roblox cookie) should stay in Replit Secrets.
#  Everything else lives here so it's easy to find and change in one place.
#
# =============================================================================

# ── Discord ───────────────────────────────────────────────────────────────────

# Your Discord server ID
GUILD_ID: int = 1468430352661086302

# ── Roblox ────────────────────────────────────────────────────────────────────

# Blackthorn Security LTD — https://www.roblox.com/communities/851531811/
ROBLOX_GROUP_ID: int = 851531811

# ── Channels (set each to the integer channel/category ID, 0 = disabled) ─────

CHANNEL_LOGS:                int = 0   # General mod-action log channel
CHANNEL_TICKET_CATEGORY:     int = 0   # Category where ticket channels are created
CHANNEL_TICKET_LOGS:         int = 0   # Ticket open / close / escalate log
CHANNEL_TRANSCRIPT:          int = 0   # Transcript saved here when ticket closes
CHANNEL_EVENT_ANNOUNCEMENTS: int = 0   # Roblox event announcements
CHANNEL_RANKING_LOGS:        int = 0   # Roblox rank-change log
CHANNEL_WELCOME:             int = 0   # New-member welcome messages

# ── Roles (exact Discord role names, case-sensitive) ──────────────────────────

ROLE_ADMIN:          str = "Admin"
ROLE_MODERATOR:      str = "Moderator"
ROLE_TICKET_SUPPORT: str = "Support"
ROLE_MUTED:          str = "Muted"
ROLE_ROBLOX_HOST:    str = "Event Host"
ROLE_VERIFIED:       str = "Verified"

# ── Ticket settings ───────────────────────────────────────────────────────────

TICKET_MAX_OPEN_PER_USER: int = 2   # Max open tickets a single user can have

# =============================================================================
#  DO NOT EDIT BELOW — this builds the config dict used by the rest of the bot
# =============================================================================

def build_config(token: str, roblox_cookie: str) -> dict:
    """Called by bot.py after secrets are loaded from the environment."""
    return {
        "token":    token,
        "guild_id": GUILD_ID,

        "roles": {
            "admin":          ROLE_ADMIN,
            "moderator":      ROLE_MODERATOR,
            "ticket_support": ROLE_TICKET_SUPPORT,
            "muted":          ROLE_MUTED,
            "roblox_host":    ROLE_ROBLOX_HOST,
            "verified":       ROLE_VERIFIED,
        },

        "channels": {
            "logs":                 CHANNEL_LOGS,
            "ticket_category":      CHANNEL_TICKET_CATEGORY,
            "ticket_logs":          CHANNEL_TICKET_LOGS,
            "transcript_channel":   CHANNEL_TRANSCRIPT,
            "event_announcements":  CHANNEL_EVENT_ANNOUNCEMENTS,
            "ranking_logs":         CHANNEL_RANKING_LOGS,
            "welcome":              CHANNEL_WELCOME,
        },

        "roblox": {
            "cookie":   roblox_cookie,
            "group_id": ROBLOX_GROUP_ID,
        },

        "ticket": {
            "max_open_per_user":  TICKET_MAX_OPEN_PER_USER,
            "transcript_channel": CHANNEL_TRANSCRIPT,
        },
    }
