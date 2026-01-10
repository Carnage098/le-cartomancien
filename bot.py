import os
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

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN manquant.")
if CHANNEL_ID == 0:
    raise RuntimeError("CHANNEL_ID manquant (id du salon #🧩・carte-du-jour).")

INTENTS = discord.Intents.default()


def load_cards(filepath: str = "cards.txt") -> list[str]:
    path = Path(filepath)
    if not path.exists():
        raise RuntimeError(f"Fichier {filepath} introuvable. Ajoute-le à la racine du repo.")

    cards: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        cards.append(s)

    # Anti-doublons simples
    cards = list(dict.fromkeys(cards))

    if len(cards) == 0:
        raise RuntimeError(f"{filepath} est vide (ou ne contient que des commentaires).")

    return cards


CARDS = load_cards("cards.txt")


class Cartomancien(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self._last_posted_date: str | None = None

    async def setup_hook(self):
        await self.tree.sync()


bot = Cartomancien()


def is_target_channel(channel) -> bool:
    return channel is not None and getattr(channel, "id", None) == CHANNEL_ID


async def send_card_of_the_day():
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        channel = await bot.fetch_channel(CHANNEL_ID)

    card = random.choice(CARDS)

    await channel.send(
        f"🧩 **Carte du jour : {card}**\n"
        "💬 Jouable aujourd’hui ? Tech ? Ou dépassée ?"
    )


@bot.event
async def on_ready():
    print(f"🧩 Le Cartomancien connecté : {bot.user} | Cartes chargées: {len(CARDS)} | TZ={TZ}")
    if not daily_card.is_running():
        daily_card.start()


@tasks.loop(minutes=1)
async def daily_card():
    now = dt.datetime.now()

    # 10:00 chaque jour
    if now.hour == 10 and now.minute == 0:
        today = now.strftime("%Y-%m-%d")
        if bot._last_posted_date != today:
            await send_card_of_the_day()
            bot._last_posted_date = today


@bot.tree.command(name="health", description="Vérifie que Le Cartomancien fonctionne.")
async def health(interaction: discord.Interaction):
    if not is_target_channel(interaction.channel):
        await interaction.response.send_message(
            "Je fonctionne uniquement dans #🧩・carte-du-jour 😉",
            ephemeral=True
        )
        return
    await interaction.response.send_message(f"🧩 En ligne ! ({len(CARDS)} cartes chargées) ✅")


@bot.tree.command(name="carte", description="Force l'affichage d'une carte au hasard.")
async def carte(interaction: discord.Interaction):
    if not is_target_channel(interaction.channel):
        await interaction.response.send_message(
            "Va dans #🧩・carte-du-jour pour utiliser cette commande 😉",
            ephemeral=True
        )
        return

    await interaction.response.send_message("🧩 Le Cartomancien consulte les cartes...")
    await send_card_of_the_day()


bot.run(DISCORD_TOKEN)
