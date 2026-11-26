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
   permissions `View Channels`, `Send Messages`, `Embed Links` et `Read Message History`, puis ouvrir l'URL générée.
   Vérifie que le bot peut voir et écrire dans le salon de lore.
3. **Clé d'IA gratuite** : par défaut le bot utilise **Gemini** (Google). Crée une clé gratuite sur
   [Google AI Studio](https://aistudio.google.com/apikey), sans carte bancaire. Voir « Choisir l'IA » plus bas pour les autres options.
4. **Lancer** (Python 3.10+) :

```bash
python3 -m venv .venv && source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env   # puis remplir DISCORD_TOKEN, GEMINI_API_KEY, WOW_REALM
```

```bash
python bot.py
```

Le serveur (`DEV_GUILD_ID`) et le salon de lore (`LORE_CHANNEL_ID`) de la guilde sont déjà configurés
par défaut. Si le salon est inaccessible, le chapitre est publié là où la commande a été lancée.

## Déploiement sur Railway

Le dépôt contient `railway.json` (commande de démarrage `python bot.py`) et `.python-version`.

1. **New Project → Deploy from GitHub repo**, choisis ce dépôt. Dans *Settings → Source*, sélectionne
   la branche qui contient le bot.
2. **Volume (indispensable)** : clic droit sur le service → *Attach Volume*, point de montage `/data`.
   Sans volume, la base est effacée à chaque redéploiement : le bot la reconstruit alors en relisant
   le salon de lore (d'où la permission `Read Message History`), mais les récits originaux des
   membres sont perdus. Le volume reste donc fortement recommandé.
3. **Variables** (onglet *Variables*, pas de fichier `.env` sur Railway) :

   | Variable | Valeur |
   |---|---|
   | `DISCORD_TOKEN` | le token du bot |
   | `GEMINI_API_KEY` | ta clé Gemini |
   | `LORE_DB_PATH` | `/data/lore.db` |
   | `WOW_REALM` | ton royaume (facultatif) |

   Le nom de guilde, le serveur et le salon ont déjà les bonnes valeurs par défaut.
4. Déploie : dans les *Deploy Logs*, tu dois voir `Connecté en tant que …`. Aucun port ni domaine n'est nécessaire.

`AI_PROVIDER=ollama` ne fonctionne pas sur Railway (pas de modèle local) : garde `gemini` ou `groq`.

## Le lore existant

`lore_canon.md` contient les faits établis (le Nom maudit et les 4 bans de la GM, le Grand Schisme…).
Le Chroniqueur les lit avant chaque chapitre et ne les contredit jamais. Ajoute-y les nouveaux
faits marquants, puis redémarre le bot.

Les noms listés dans `LORE_FORBIDDEN_NAMES` ne sont jamais écrits : le Chroniqueur a pour consigne
d'utiliser un surnom, et le nom est remplacé automatiquement s'il apparaît quand même.

## Le prologue

Au premier démarrage, si la saga est encore vide, le bot publie automatiquement dans le salon de lore
les chapitres d'ouverture écrits dans `prologue.md` :

1. **Jess et le Nom maudit** : la fondation de la guilde par Jess, les quatre bans, le nouveau nom.
2. **Le Grand Schisme** : l'affaire de l'Ombre Pourpre.
3. **La Grande Course au 60** : Urkan, Timo Teh, Rhéa et Théo dans la course au premier 60.

Un chapitre ajouté plus tard à `prologue.md` est publié au démarrage suivant, à la suite de la saga.
Les chapitres déjà publiés ne sont jamais republiés (le titre sert de repère : ne le modifie pas après publication).

## Choisir l'IA

Le fournisseur se règle avec `AI_PROVIDER` dans `.env` :

| `AI_PROVIDER` | Prix | Clé | Remarques |
|---|---|---|---|
| `gemini` (défaut) | Gratuit | `GEMINI_API_KEY` ([AI Studio](https://aistudio.google.com/apikey)) | Très bon en français. Sur l'offre gratuite, Google peut utiliser les textes envoyés pour améliorer ses produits. |
| `groq` | Gratuit | `GROQ_API_KEY` ([console Groq](https://console.groq.com/keys)) | Très rapide, modèles open source (Llama…). |
| `ollama` | Gratuit, local | aucune | Installer [Ollama](https://ollama.com) puis `ollama pull mistral-small` sur la machine du bot. Demande un PC assez puissant, rien ne sort de chez toi. |
| `claude` | Payant | `ANTHROPIC_API_KEY` | Meilleure qualité d'écriture. Nécessite `pip install anthropic`. |

Les offres gratuites ont des limites (requêtes par minute / par jour), largement suffisantes pour une guilde.
Si un modèle par défaut est retiré par le fournisseur, indique-en un autre avec `AI_MODEL`.
Avec Gemini, si le modèle principal est surchargé (erreur 503), hors quota ou retiré, le bot essaie
automatiquement des modèles de secours (`gemini-3-flash-preview`, `gemini-3.5-flash-lite`,
`gemini-flash-lite-latest`). La liste se change avec `AI_FALLBACK_MODELS`.

## Fonctionnement

- `bot.py` — commandes slash et formulaire (modal Discord).
- `lore_writer.py` — prompt du Chroniqueur et appel à l'IA choisie.
  Le ton, la longueur et le style se règlent dans `SYSTEM_PROMPT`.
- `lore_canon.md` — faits établis de la saga.
- `prologue.md` — chapitres d'ouverture publiés au premier démarrage.
- `lore_store.py` — chapitres stockés dans SQLite (`lore.db`), séparés par serveur Discord.

Chaque appel envoie toute la saga existante au modèle pour garder la cohérence.
