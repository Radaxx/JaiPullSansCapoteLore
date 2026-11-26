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


writer = LoreWriter(
    GUILD_NAME,
    REALM,
    load_canon(CANON_PATH),
    FORBIDDEN_NAMES,
    provider=os.getenv("AI_PROVIDER", "gemini"),
    model=os.getenv("AI_MODEL") or None,
    base_url=os.getenv("AI_BASE_URL") or None,
    fallback_models=(
        os.environ["AI_FALLBACK_MODELS"].split(",") if "AI_FALLBACK_MODELS" in os.environ else None
    ),
)


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


CHAPTER_TITLE_RE = re.compile(r"^📜 Chapitre (\d+) — (.+)$")
PROLOGUE_FOOTER = "Prologue"


def _chapter_title(message: discord.Message, bot_user: discord.abc.User) -> str | None:
    """Titre du chapitre si le message est un chapitre publié par le bot, sinon None."""
    if message.author.id != bot_user.id or not message.embeds:
        return None
    match = CHAPTER_TITLE_RE.match(message.embeds[0].title or "")
    return match.group(2) if match else None


async def sync_from_channel(client: discord.Client) -> None:
    """Relit le salon de lore au démarrage.

    - Si la base est vide (par exemple après un redéploiement sans volume), la saga est
      reconstruite à partir des chapitres déjà publiés dans le salon.
    - Les chapitres du prologue publiés en double sont supprimés (on garde le plus ancien).
    """
    if not DEV_GUILD_ID or client.user is None:
        return
    channel = await get_lore_channel(client)
    if channel is None:
        return
    guild_id = int(DEV_GUILD_ID)
    restore = not store.all_chapters(guild_id)
    seen_prologue: set[str] = set()
    restored = removed = 0
    try:
        async for message in channel.history(limit=None, oldest_first=True):
            title = _chapter_title(message, client.user)
            if title is None:
                continue
            footer = message.embeds[-1].footer.text or ""
            is_prologue = footer.startswith(PROLOGUE_FOOTER)
            if is_prologue:
                if title in seen_prologue:
                    await message.delete()
                    removed += 1
                    continue
                seen_prologue.add(title)
            if restore:
                text = "\n".join(e.description or "" for e in message.embeds).strip()
                if is_prologue:
                    author_id, author = 0, "Le Chroniqueur"
                else:
                    author_id = -1  # auteur inconnu après restauration
                    author = footer.removeprefix("D'après le récit de ").rsplit(" · ", 1)[0]
                store.add_chapter(guild_id, title, text, "(restauré depuis Discord)", author_id, author)
                restored += 1
    except discord.Forbidden:
        log.warning("Impossible de lire l'historique du salon de lore (permission manquante).")
        return
    if restored:
        log.info("Saga reconstruite depuis le salon : %s chapitre(s).", restored)
    if removed:
        log.info("%s chapitre(s) du prologue en double supprimé(s) du salon.", removed)


async def delete_published_chapter(client: discord.Client, chapter: Chapter) -> bool:
    """Supprime du salon de lore le message d'un chapitre (parmi les 200 derniers messages)."""
    channel = await get_lore_channel(client)
    if channel is None or client.user is None:
        return False
    try:
        # Le plus récent message portant ce titre (le numéro affiché peut différer après une
        # reconstruction de la saga).
        async for message in channel.history(limit=200):
            if _chapter_title(message, client.user) == chapter.title:
                await message.delete()
                return True
    except discord.Forbidden:
        log.warning("Impossible de supprimer le chapitre du salon de lore.")
    return False


async def seed_prologue(client: discord.Client) -> None:
    """Publie dans le salon de lore les chapitres du prologue qui n'ont pas encore été publiés.

    Un chapitre ajouté plus tard à prologue.md est publié au démarrage suivant, à la suite
    de la saga existante.
    """
    if not DEV_GUILD_ID:
        return
    guild_id = int(DEV_GUILD_ID)
    published = {c.title for c in store.all_chapters(guild_id) if c.author_id == 0}
    missing = [(t, b) for t, b in load_prologue(PROLOGUE_PATH) if t not in published]
    if not missing:
        return
    channel = await get_lore_channel(client)
    for title, text in missing:
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
            "Ex : Urkan a pex jusqu'à 4h du mat, Théo est mort en tombant d'un pont…"
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
        self._synced = False

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
        if self._synced:  # on_ready est rappelé à chaque reconnexion
            return
        self._synced = True
        await sync_from_channel(self)
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
        await interaction.response.defer(ephemeral=True)
        deleted = await delete_published_chapter(interaction.client, removed)
        note = "" if deleted else " (message introuvable dans le salon : supprime-le à la main)"
        await interaction.followup.send(
            f"🗑️ Chapitre {removed.number} « {removed.title} » effacé des archives{note}.",
            ephemeral=True,
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Chroniqueur().run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
