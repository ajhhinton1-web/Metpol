import discord
import json
import os
import sys
from datetime import datetime

# ── Colour palette ────────────────────────────────────────────────────────────
GREEN  = discord.Color.from_str("#57F287")
RED    = discord.Color.from_str("#ED4245")
YELLOW = discord.Color.from_str("#FEE75C")
BLUE   = discord.Color.from_str("#5865F2")
ORANGE = discord.Color.from_str("#E67E22")
PURPLE = discord.Color.from_str("#9B59B6")
CYAN   = discord.Color.from_str("#1ABC9C")


def success_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=f"✅  {title}", description=description,
                         color=GREEN, timestamp=datetime.utcnow())

def error_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=f"❌  {title}", description=description,
                         color=RED, timestamp=datetime.utcnow())

def info_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=f"ℹ️  {title}", description=description,
                         color=BLUE, timestamp=datetime.utcnow())

def warn_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=f"⚠️  {title}", description=description,
                         color=YELLOW, timestamp=datetime.utcnow())


# ── JSON file store ───────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

def _path(name: str) -> str:
    return os.path.join(DATA_DIR, f"{name}.json")

def load_data(name: str) -> dict:
    p = _path(name)
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)

def save_data(name: str, data: dict):
    with open(_path(name), "w") as f:
        json.dump(data, f, indent=2)


# ── Config — built from settings.py + env secrets ────────────────────────────
def get_config() -> dict:
    # Ensure the project root is importable
    root = os.path.join(os.path.dirname(__file__), "..")
    if root not in sys.path:
        sys.path.insert(0, root)
    import settings as s
    token        = os.environ.get("DISCORD_TOKEN", "")
    roblox_cookie = os.environ.get("ROBLOX_COOKIE", "")
    return s.build_config(token=token, roblox_cookie=roblox_cookie)


# ── Permission helper ─────────────────────────────────────────────────────────
def has_role(member: discord.Member, role_name: str) -> bool:
    return any(r.name == role_name for r in member.roles)
