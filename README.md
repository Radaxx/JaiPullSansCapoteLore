# 📜 Le Chroniqueur — bot de lore pour la guilde

Un bot Discord qui transforme les récits des membres (raids, wipes, loots, conneries en vocal…)
en **chapitres romancés** de la saga de la guilde, façon roman de fantasy Warcraft.
Chaque nouveau chapitre tient compte des précédents : personnages récurrents, running gags, rivalités.

## Commandes

| Commande | Effet |
|---|---|
| `/lore ecrire` | Ouvre un formulaire : tu racontes ce qui s'est passé, le bot publie le chapitre romancé dans le salon de lore |
| `/lore chapitre [numero]` | Relit un chapitre (le dernier par défaut) |
| `/lore sommaire` | Table des matières de la saga |
| `/lore resume` | Résumé épique de toute la saga |
| `/lore annuler` | Supprime le dernier chapitre (permission « Gérer les messages ») |

## Installation

1. **Créer le bot Discord** sur le [Developer Portal](https://discord.com/developers/applications) :
   *New Application* → onglet **Bot** → *Reset Token* (à copier).
   Aucun intent privilégié n'est nécessaire.
2. **Inviter le bot** : onglet *OAuth2 → URL Generator*, cocher `bot` et `applications.commands`,
   permissions `View Channels`, `Send Messages` + `Embed Links`, puis ouvrir l'URL générée.
   Vérifie que le bot peut voir et écrire dans le salon de lore.
3. **Clé API Claude** : à créer sur [console.anthropic.com](https://console.anthropic.com).
4. **Lancer** (Python 3.10+) :

```bash
python3 -m venv .venv && source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env   # puis remplir DISCORD_TOKEN, ANTHROPIC_API_KEY, GUILD_NAME, WOW_REALM
```

```bash
python bot.py
```

Le serveur (`DEV_GUILD_ID`) et le salon de lore (`LORE_CHANNEL_ID`) de la guilde sont déjà configurés
par défaut. Si le salon est inaccessible, le chapitre est publié là où la commande a été lancée.

## Le lore existant

`lore_canon.md` contient les faits établis (le Nom maudit et les 4 bans de la GM, le Grand Schisme…).
Le Chroniqueur les lit avant chaque chapitre et ne les contredit jamais. Ajoute-y les nouveaux
faits marquants, puis redémarre le bot.

Les noms listés dans `LORE_FORBIDDEN_NAMES` ne sont jamais écrits : le Chroniqueur a pour consigne
d'utiliser un surnom, et le nom est remplacé automatiquement s'il apparaît quand même.

## Fonctionnement

- `bot.py` — commandes slash et formulaire (modal Discord).
- `lore_writer.py` — prompt du Chroniqueur et appel à l'API Claude (`claude-opus-5-5`).
  Le ton, la longueur et le style se règlent dans `SYSTEM_PROMPT`.
- `lore_canon.md` — faits établis de la saga.
- `lore_store.py` — chapitres stockés dans SQLite (`lore.db`), séparés par serveur Discord.

Chaque appel envoie toute la saga existante au modèle pour garder la cohérence ; le cache de prompt
réduit le coût des appels successifs. Si le modèle décline un récit, l'API bascule automatiquement
sur un modèle de secours (`fallbacks="default"`).
