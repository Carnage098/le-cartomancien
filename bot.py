import os
import json
import random
import datetime as dt
from pathlib import Path

import discord
from discord.ext import commands, tasks

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
TZ = os.getenv("TZ", "Europe/Paris")

# Anti-doublon : nombre de jours pendant lesquels une carte ne doit PAS revenir
NO_REPEAT_DAYS = int(os.getenv("NO_REPEAT_DAYS", "60"))

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN manquant.")
if CHANNEL_ID == 0:
    raise RuntimeError("CHANNEL_ID manquant (id du salon #🧩・carte-du-jour).")

INTENTS = discord.Intents.default()

STATE_PATH = Path("state.json")
CARDS_PATH = Path("cards.txt")


def load_cards() -> list[str]:
    if not CARDS_PATH.exists():
        raise RuntimeError("cards.txt introuvable à la racine du repo.")

    cards: list[str] = []
    for line in CARDS_PATH.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        cards.append(s)

    # Anti-doublons dans le fichier lui-même
    cards = list(dict.fromkeys(cards))

    if not cards:
        raise RuntimeError("cards.txt est vide (ou ne contient que des commentaires).")

    return cards


CARDS = load_cards()


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"last_posted_date": None, "history": []}  # history = [{"date": "YYYY-MM-DD", "card": "..."}]
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        # Si le fichier est corrompu, on repart clean
        return {"last_posted_date": None, "history": []}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def today_str(now: dt.datetime | None = None) -> str:
    if now is None:
        now = dt.datetime.now()
    return now.strftime("%Y-%m-%d")


def recent_cards_set(state: dict, now: dt.datetime) -> set[str]:
    """Retourne l'ensemble des cartes postées dans les NO_REPEAT_DAYS derniers jours."""
    cutoff = now.date() - dt.timedelta(days=NO_REPEAT_DAYS)

    recent: set[str] = set()
    history = state.get("history", [])
    for entry in history:
        try:
            d = dt.date.fromisoformat(entry["date"])
            if d >= cutoff:
                recent.add(entry["card"])
        except Exception:
            continue
    return recent


def pick_card_no_repeat(state: dict, now: dt.datetime) -> str:
    """Choisit une carte qui n'est pas dans l'historique récent. Si impossible, fallback random."""
    recent = recent_cards_set(state, now)

    candidates = [c for c in CARDS if c not in recent]
    if candidates:
        return random.choice(candidates)

    # Si tout est bloqué (ex: NO_REPEAT_DAYS trop grand par rapport à la taille de CARDS), on fallback.
    return random.choice(CARDS)


class Cartomancien(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.state = load_state()

    async def setup_hook(self):
        await self.tree.sync()


bot = Cartomancien()


def is_target_channel(channel) -> bool:
    return channel is not None and getattr(channel, "id", None) == CHANNEL_ID


async def send_card_of_the_day(now: dt.datetime, forced: bool = False) -> None:
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        channel = await bot.fetch_channel(CHANNEL_ID)

    card = pick_card_no_repeat(bot.state, now)

    # Message
    msg = await channel.send(
        f"🧩 **Carte du jour : {card}**\n"
        f"🗳️ Votez : 👍 jouable | 👎 dépassée | 🔥 iconique\n"
        f"⏳ Anti-doublon : {NO_REPEAT_DAYS} jours"
    )

    # Votes automatiques (réactions)
    for emoji in ("👍", "👎", "🔥"):
        try:
            await msg.add_reaction(emoji)
        except Exception:
            # Si le bot n'a pas la permission d'ajouter des réactions, ça ne doit pas crasher.
            pass

    # On enregistre dans l'historique si ce n'est pas un "forced" ou si tu veux aussi l'enregistrer
    # Ici: on enregistre TOUJOURS, comme ça l'anti-doublon fonctionne même avec /carte.
    entry = {"date": today_str(now), "card": card}
    bot.state.setdefault("history", []).append(entry)

    # On purge l'historique pour garder un fichier léger (garde ~400 jours)
    # (ça ne change pas l'anti-doublon puisque NO_REPEAT_DAYS << 400)
    max_keep_days = 400
    cutoff = now.date() - dt.timedelta(days=max_keep_days)
    new_hist = []
    for e in bot.state.get("history", []):
        try:
            d = dt.date.fromisoformat(e["date"])
            if d >= cutoff:
                new_hist.append(e)
        except Exception:
            continue
    bot.state["history"] = new_hist

    save_state(bot.state)


@bot.event
async def on_ready():
    print(
        f"🧩 Le Cartomancien connecté : {bot.user} | Cartes: {len(CARDS)} | "
        f"Anti-doublon: {NO_REPEAT_DAYS} jours | TZ={TZ}"
    )
    if not daily_card.is_running():
        daily_card.start()


@tasks.loop(minutes=1)
async def daily_card():
    now = dt.datetime.now()
    if now.hour == 10 and now.minute == 0:
        today = today_str(now)
        last = bot.state.get("last_posted_date")

        if last != today:
            await send_card_of_the_day(now)
            bot.state["last_posted_date"] = today
            save_state(bot.state)


# ----- Slash commands -----
@bot.tree.command(name="health", description="Vérifie que Le Cartomancien fonctionne.")
async def health(interaction: discord.Interaction):
    if not is_target_channel(interaction.channel):
        await interaction.response.send_message(
            "Je fonctionne uniquement dans #🧩・carte-du-jour 😉",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"🧩 En ligne ✅ | {len(CARDS)} cartes | Anti-doublon: {NO_REPEAT_DAYS} jours"
    )


@bot.tree.command(name="carte", description="Force l'affichage d'une carte (anti-doublon actif).")
async def carte(interaction: discord.Interaction):
    if not is_target_channel(interaction.channel):
        await interaction.response.send_message(
            "Va dans #🧩・carte-du-jour pour utiliser cette commande 😉",
            ephemeral=True
        )
        return

    now = dt.datetime.now()
    await interaction.response.send_message("🧩 Le Cartomancien consulte les cartes...")
    await send_card_of_the_day(now, forced=True)


bot.run(DISCORD_TOKEN)
