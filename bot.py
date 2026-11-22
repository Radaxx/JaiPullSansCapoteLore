"""Bot Discord « Chroniqueur » : transforme les récits des membres en lore romancé de la guilde."""

from __future__ import annotations

import logging
import os
import re

import discord
from discord import app_commands
from dotenv import load_dotenv

from lore_store import Chapter, LoreStore
from lore_writer import LoreWriter, LoreWriterError

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_NAME = os.getenv("GUILD_NAME", "J'ai pull sans protection")
REALM = os.getenv("WOW_REALM", "un royaume d'Azeroth")
DB_PATH = os.getenv("LORE_DB_PATH", "lore.db")
# Serveur Discord de la guilde : les commandes y sont synchronisées instantanément.
DEV_GUILD_ID = os.getenv("DEV_GUILD_ID", "1569153457204633740")
# Salon où chaque nouveau chapitre est publié (vide = publier là où la commande a été lancée).
LORE_CHANNEL_ID = os.getenv("LORE_CHANNEL_ID", "1574017730900791376")
# Faits établis de la saga, lus par le Chroniqueur avant chaque chapitre.
CANON_PATH = os.getenv("LORE_CANON_PATH", "lore_canon.md")
# Chapitres d'ouverture publiés au premier démarrage, si la saga du serveur est vide.
PROLOGUE_PATH = os.getenv("LORE_PROLOGUE_PATH", "prologue.md")
# Noms à ne jamais écrire dans la saga (séparés par des virgules).
FORBIDDEN_NAMES = os.getenv("LORE_FORBIDDEN_NAMES", "Violette").split(",")

EMBED_COLOR = discord.Color.from_rgb(201, 162, 39)  # or « légendaire »
EMBED_LIMIT = 4000  # limite Discord : 4096 caractères par description d'embed

log = logging.getLogger("chroniqueur")
store = LoreStore(DB_PATH)


def load_canon(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        log.warning("Fichier de lore %s introuvable, le Chroniqueur part de zéro.", path)
        return ""


writer = LoreWriter(GUILD_NAME, REALM, load_canon(CANON_PATH), FORBIDDEN_NAMES)


def load_prologue(path: str) -> list[tuple[str, str]]:
    """Lit le prologue : une section « ## Titre » par chapitre. Renvoie [(titre, texte)]."""
    text = load_canon(path)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    chapters = []
    for section in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
        title, _, body = section.partition("\n")
        if title.strip() and body.strip():
            chapters.append((title.strip(), body.strip()))
    return chapters


async def seed_prologue(client: discord.Client) -> None:
    """Publie le prologue dans le salon de lore si la saga du serveur est encore vide."""
    if not DEV_GUILD_ID:
        return
    guild_id = int(DEV_GUILD_ID)
    if store.all_chapters(guild_id):
        return
    prologue = load_prologue(PROLOGUE_PATH)
    if not prologue:
        return
    channel = await get_lore_channel(client)
    for title, text in prologue:
        chapter = store.add_chapter(guild_id, title, text, "(prologue)", 0, "Le Chroniqueur")
        log.info("Prologue : chapitre %s « %s » ajouté.", chapter.number, title)
        if channel is not None:
            try:
                await channel.send(embeds=chapter_embeds(chapter)[:10])
            except discord.Forbidden:
                log.warning("Pas la permission d'écrire dans le salon de lore.")
                channel = None


async def get_lore_channel(client: discord.Client) -> discord.abc.Messageable | None:
    """Renvoie le salon dédié au lore, ou None s'il n'est pas configuré / accessible."""
    if not LORE_CHANNEL_ID:
        return None
    channel_id = int(LORE_CHANNEL_ID)
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden):
            log.warning("Salon de lore %s inaccessible.", channel_id)
            return None
    return channel if isinstance(channel, discord.abc.Messageable) else None


def split_text(text: str, limit: int = EMBED_LIMIT) -> list[str]:
    """Découpe un texte par paragraphes pour respecter la limite des embeds."""
    chunks: list[str] = []
    current = ""
    for para in text.split("\n"):
        while len(para) > limit:
            chunks.append(para[:limit])
            para = para[limit:]
        if len(current) + len(para) + 1 > limit:
            chunks.append(current.rstrip())
            current = ""
        current += para + "\n"
    if current.strip():
        chunks.append(current.rstrip())
    return chunks or [""]


def chapter_embeds(chapter: Chapter) -> list[discord.Embed]:
    parts = split_text(chapter.text)
    embeds = []
    for i, part in enumerate(parts):
        embed = discord.Embed(description=part, color=EMBED_COLOR)
        if i == 0:
            embed.title = f"📜 Chapitre {chapter.number} — {chapter.title}"
        if i == len(parts) - 1:
            origin = "Prologue" if chapter.author_id == 0 else f"D'après le récit de {chapter.author_name}"
            embed.set_footer(text=f"{origin} · {GUILD_NAME}")
        embeds.append(embed)
    return embeds


class LoreModal(discord.ui.Modal, title="Raconte un exploit de la guilde"):
    recit = discord.ui.TextInput(
        label="Que s'est-il passé ?",
        style=discord.TextStyle.paragraph,
        placeholder=(
            "Ex : Hier soir en raid, Grumly a pull le boss pendant que le heal était AFK. "
            "Wipe. Puis on l'a down au 12e try et Lysa a loot l'arme !"
        ),
        min_length=10,
        max_length=4000,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild_id = interaction.guild_id
        author = interaction.user.display_name
        try:
            title, text = await writer.write_chapter(
                store.all_chapters(guild_id), author, self.recit.value
            )
        except LoreWriterError as e:
            await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
            return
        chapter = store.add_chapter(
            guild_id, title, text, self.recit.value, interaction.user.id, author
        )
        embeds = chapter_embeds(chapter)[:10]

        channel = await get_lore_channel(interaction.client)
        if channel is not None:
            try:
                message = await channel.send(embeds=embeds)
                await interaction.followup.send(
                    f"✅ Ton récit est devenu le **chapitre {chapter.number}** : {message.jump_url}",
                    ephemeral=True,
                )
                return
            except discord.Forbidden:
                log.warning("Pas la permission d'écrire dans le salon de lore.")
        # Pas de salon dédié utilisable : publication là où la commande a été lancée.
        if interaction.channel is not None:
            await interaction.channel.send(embeds=embeds)
            await interaction.followup.send(
                f"✅ Chapitre {chapter.number} publié ici (salon de lore inaccessible).",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(embeds=embeds)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.exception("Erreur dans le formulaire de lore", exc_info=error)
        send = (
            interaction.followup.send
            if interaction.response.is_done()
            else interaction.response.send_message
        )
        await send("⚠️ Une erreur inattendue est survenue.", ephemeral=True)


class Chroniqueur(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.tree.add_command(lore_group)
        if DEV_GUILD_ID:
            guild = discord.Object(id=int(DEV_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        log.info("Connecté en tant que %s", self.user)
        await seed_prologue(self)


lore_group = app_commands.Group(
    name="lore", description="La saga romancée de la guilde", guild_only=True
)


@lore_group.command(name="ecrire", description="Raconte un événement et le Chroniqueur en fera un chapitre")
async def lore_ecrire(interaction: discord.Interaction) -> None:
    await interaction.response.send_modal(LoreModal())


@lore_group.command(name="chapitre", description="Relire un chapitre de la saga")
@app_commands.describe(numero="Numéro du chapitre (par défaut : le dernier)")
async def lore_chapitre(interaction: discord.Interaction, numero: int | None = None) -> None:
    assert interaction.guild_id is not None
    chapters = store.all_chapters(interaction.guild_id)
    if not chapters:
        await interaction.response.send_message(
            "La saga n'a pas encore commencé. Utilise `/lore ecrire` !", ephemeral=True
        )
        return
    chapter = chapters[-1] if numero is None else store.get_chapter(interaction.guild_id, numero)
    if chapter is None:
        await interaction.response.send_message(
            f"Ce chapitre n'existe pas (la saga en compte {len(chapters)}).", ephemeral=True
        )
        return
    await interaction.response.send_message(embeds=chapter_embeds(chapter)[:10])


@lore_group.command(name="sommaire", description="Table des matières de la saga")
async def lore_sommaire(interaction: discord.Interaction) -> None:
    assert interaction.guild_id is not None
    chapters = store.all_chapters(interaction.guild_id)
    if not chapters:
        await interaction.response.send_message(
            "La saga n'a pas encore commencé. Utilise `/lore ecrire` !", ephemeral=True
        )
        return
    lines = [f"**{c.number}.** {c.title} — *{c.author_name}*" for c in chapters]
    embeds = [
        discord.Embed(
            title=f"📖 La Saga de {GUILD_NAME}" if i == 0 else None,
            description=part,
            color=EMBED_COLOR,
        )
        for i, part in enumerate(split_text("\n".join(lines)))
    ]
    await interaction.response.send_message(embeds=embeds[:10])


@lore_group.command(name="resume", description="Le Chroniqueur résume toute la saga")
async def lore_resume(interaction: discord.Interaction) -> None:
    assert interaction.guild_id is not None
    chapters = store.all_chapters(interaction.guild_id)
    if not chapters:
        await interaction.response.send_message(
            "La saga n'a pas encore commencé. Utilise `/lore ecrire` !", ephemeral=True
        )
        return
    await interaction.response.defer(thinking=True)
    try:
        summary = await writer.summarize(chapters)
    except LoreWriterError as e:
        await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
        return
    embed = discord.Embed(
        title=f"✨ La Saga de {GUILD_NAME} — en résumé",
        description=split_text(summary)[0],
        color=EMBED_COLOR,
    )
    embed.set_footer(text=f"{len(chapters)} chapitre(s) écrits à ce jour")
    await interaction.followup.send(embed=embed)


@lore_group.command(name="annuler", description="Supprime le dernier chapitre (officiers uniquement)")
@app_commands.default_permissions(manage_messages=True)
async def lore_annuler(interaction: discord.Interaction) -> None:
    assert interaction.guild_id is not None
    removed = store.delete_last(interaction.guild_id)
    if removed is None:
        await interaction.response.send_message("Il n'y a aucun chapitre à supprimer.", ephemeral=True)
    else:
        await interaction.response.send_message(
            f"🗑️ Chapitre {removed.number} « {removed.title} » effacé des archives.", ephemeral=True
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Chroniqueur().run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
