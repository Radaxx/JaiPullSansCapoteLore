# 📜 Le Chroniqueur — bot de lore pour la guilde

Un bot Discord qui transforme les récits des membres (raids, wipes, loots, conneries en vocal…)
en **chapitres romancés** de la saga de la guilde, façon roman de fantasy Warcraft.
Chaque nouveau chapitre tient compte des précédents : personnages récurrents, running gags, rivalités.

## Commandes

| Commande | Effet |
|---|---|
| `/lore ecrire` | Ouvre un formulaire : tu racontes ce qui s'est passé, le bot publie le chapitre romancé |
| `/lore chapitre [numero]` | Relit un chapitre (le dernier par défaut) |
| `/lore sommaire` | Table des matières de la saga |
| `/lore resume` | Résumé épique de toute la saga |
| `/lore annuler` | Supprime le dernier chapitre (permission « Gérer les messages ») |

## Installation

1. **Créer le bot Discord** sur le [Developer Portal](https://discord.com/developers/applications) :
   *New Application* → onglet **Bot** → *Reset Token* (à copier).
   Aucun intent privilégié n'est nécessaire.
2. **Inviter le bot** : onglet *OAuth2 → URL Generator*, cocher `bot` et `applications.commands`,
   permissions `Send Messages` + `Embed Links`, puis ouvrir l'URL générée.
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

Astuce : renseigne `DEV_GUILD_ID` (clic droit sur le serveur → *Copier l'identifiant*, mode développeur activé)
pour que les commandes apparaissent immédiatement ; sinon la synchronisation globale peut prendre jusqu'à une heure.

## Fonctionnement

- `bot.py` — commandes slash et formulaire (modal Discord).
- `lore_writer.py` — prompt du Chroniqueur et appel à l'API Claude (`claude-opus-5-5`).
  Le ton, la longueur et le style se règlent dans `SYSTEM_PROMPT`.
- `lore_store.py` — chapitres stockés dans SQLite (`lore.db`), séparés par serveur Discord.

Chaque appel envoie toute la saga existante au modèle pour garder la cohérence ; le cache de prompt
réduit le coût des appels successifs. Si le modèle décline un récit, l'API bascule automatiquement
sur un modèle de secours (`fallbacks="default"`).
