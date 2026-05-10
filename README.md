# Voice of Customer — MVP Abritel (soutenance)

> Plateforme d'écoute multi-canal qui transforme les avis Trustpilot / Google Play / App Store
> de **Abritel, Airbnb et Booking** en **tickets Notion** actionnables routés vers les équipes
> métier, avec notifications Slack.

Stack : **Airflow** (orchestration) · **dbt** + **Postgres** (warehouse + transformations) ·
**Python** (scraping + filtrage heuristique) · **Ollama** (catégorisation LLM fallback) ·
**Notion** (ticketing) · **Slack** (notifications) · **Docker Compose** (Postgres + Airflow).

> **Visualisation** : la couche BI est **externe** au compose. Power BI (ou tout autre
> client SQL : Tableau, Metabase, DBeaver…) se connecte directement à Postgres
> via `localhost:5433`, base `voc`, schéma `marts`. Pour des variantes intégrées
> dans le compose, voir les branches `dashboards-grafana` et `dashboards-superset`.

📐 **Documentation technique complète** : [`docs/architecture.md`](docs/architecture.md) — schémas Mermaid, modèle dimensionnel, choix techniques justifiés, conventions critiques, limites du MVP.

---

## Architecture (3 phases)

```
                    PHASE 1 : Collecte & Raffinement
        ┌─────────────────────────────────────────────────────┐
        │  Trustpilot      Google Play       App Store        │
        │      │                │                 │           │
        │      └────────┬───────┴─────────┬───────┘           │
        │       (scrapers Python, par marque × source)        │
        │                       │                             │
        │              data/bronze/*.parquet                  │
        │                       │                             │
        │       Quality filter (heuristique) + Catégorisation │
        │                  (mots-clés FR/EN)                  │
        └───────────────────────┬─────────────────────────────┘
                                ▼
                  ┌─────────────────────────────┐
                  │   PHASE 2 : Data Warehouse  │
                  │   Postgres — base `voc`     │
                  │                             │
                  │  raw.raw_reviews            │
                  │       ▼ dbt                 │
                  │  staging.stg_reviews        │
                  │       ▼                     │
                  │  intermediate.int_*         │
                  │       ▼                     │
                  │  marts.dim_*  + fact_*      │
                  └─────────────┬───────────────┘
                                ▼
        ┌─────────────────────────────────────────────────────┐
        │              PHASE 3 : Activation Métier            │
        │                                                     │
        │   dm_sav_tickets       → équipe SAV                 │
        │   dm_marketing_voc     → équipe Marketing           │
        │   dm_finance_litiges   → équipe Finance             │
        │   dm_direction_synthese→ Comité de direction        │
        │                                                     │
        │   ↓ Power BI (externe) en SQL sur marts.dm_*        │
        │   ↓ alerts.csv (spike 7j vs baseline 4 sem)         │
        │   ↓ tickets.csv (avis critiques → équipes owner)    │
        └─────────────────────────────────────────────────────┘
```

Toutes les marques sont ingérées et traitées **sans distinction** dans le pipeline.
Le benchmark Abritel ↔ Airbnb ↔ Booking se fait dans la couche de visualisation
(les marts `dm_marketing_voc` et `dm_direction_synthese` exposent les comparaisons).

---

## Démarrage rapide

Pré-requis : **Docker Desktop** ou **OrbStack** (Compose v2).

```bash
# 1. (optionnel) Copier .env.example en .env pour ajuster les paramètres
cp .env.example .env

# 2. Build + démarrage de la stack
docker compose up -d --build

# 3. Ouvrir Airflow UI : http://localhost:8080  (airflow / airflow par défaut, surchargeable via .env)
#    Activer le DAG `voc_pipeline` et le déclencher manuellement.

# 4. Power BI (ou autre BI / client SQL) : connexion externe au Postgres
#    host=localhost  port=5433  user=postgres  password=postgres  database=voc
#    schéma `marts`, tables `dm_*` (data marts métier) ou `fact_*`/`dim_*` pour SQL custom.

# 5. Postgres exposé sur le port hôte 5433 (5432 souvent déjà pris)
#    Connexion depuis un client SQL : host=localhost, port=5433, user=postgres, pwd=postgres, db=airflow

# 6. Une fois le run terminé :
#    - DWH : Postgres base `voc`, schéma `marts` (tables dm_* pour les dashboards)
#    - Fichiers locaux sous data/ :
ls data/
# alerts.csv              → spikes détectés
# tickets.csv             → backlog SAV/Finance/Produit
```

Tout couper :
```bash
docker compose down            # garde les données
docker compose down -v         # repart de zéro (postgres + warehouse)
```

---

## Le DAG `voc_pipeline`

| Tâche | Type | Rôle |
|---|---|---|
| `extract` | Python | Scrape les 3 sources × 3 marques → `data/bronze/raw_reviews_<runid>.parquet` |
| `refine_and_load` | Python | Quality filter + catégorisation heuristique + chargement Postgres `raw.raw_reviews` |
| `llm_classify` | Python | Reclasse les avis `non_classe` via Ollama (best-effort, non-bloquant) |
| `dbt_seed` | Bash | Charge les seeds dimensionnelles (brands, sources, categories…) |
| `dbt_run` | Bash | Construit staging → intermediate → marts (dims + facts + dm_*) |
| `dbt_test` | Bash | Vérifie unicité, non-nullité, accepted_values |
| `generate_alerts` | Python | Détection de pic hebdo vs baseline 4 semaines (`alerts.csv`) |
| `generate_tickets` | Python | Tickets pour chaque avis critique (`tickets.csv` audit + Notion idempotent) |
| `notify_slack` | Python | Récap webhook Slack (skip silencieux si rien à signaler) |

Cadence : **`@daily`**. La fenêtre de scraping est glissante (30j par défaut, cf. `VOC_SCRAPE_WINDOW_DAYS`).
Cap dur de **100 avis par (source × marque)** par défaut (cf. `VOC_MAX_REVIEWS_PER_SOURCE`).

---

## Schéma Postgres

Postgres héberge **deux databases** dans la même instance :
- `airflow` : metadata Airflow (DAG runs, users, connections — usage interne).
- `voc` : data warehouse, organisé en 4 schémas dbt.

**Star schema** dans la DB `voc` (source de vérité : modèles dbt sous `dbt/models/`) :

- **Dimensions** (schéma `marts`) : `dim_brand`, `dim_source`, `dim_category`, `dim_severity`, `dim_persona`, `dim_date`, `dim_ticket_status`
- **Faits** (schéma `marts`) : `fact_reviews`, `fact_classifications`, `fact_tickets`
- **Data marts** (schéma `marts`) : `dm_sav_tickets`, `dm_marketing_voc`, `dm_finance_litiges`, `dm_direction_synthese`
- **Source brute** (schéma `raw`) : `raw_reviews` (alimenté par `voc.warehouse.loader`)
- **Étages dbt** : `staging.stg_reviews` (view), `intermediate.int_reviews_classified` (view)

Inspection rapide :
```bash
# Depuis le Mac (Postgres exposé sur localhost:5433) :
psql -h localhost -p 5433 -U postgres -d voc -c "SELECT brand_label, COUNT(*) FROM marts.dm_marketing_voc GROUP BY 1;"

# Ou via le conteneur :
docker compose exec postgres psql -U postgres -d voc -c "\\dn"  # liste les schémas
docker compose exec postgres psql -U postgres -d voc -c "\\dt marts.*"  # tables marts
```

---

## Quality filter (Phase 1b)

Heuristiques déterministes appliquées avant la modélisation. Un avis est `is_exploitable=False`
si l'une de ces règles match (motif stocké dans `exclusion_reason`) :

| Motif | Règle |
|---|---|
| `vide` | texte `null` ou whitespace |
| `placeholder` | `(sans commentaire)`, `n/a`, `…` |
| `trop_court` | < 5 caractères ou < 2 mots |
| `non_textuel` | < 3 lettres après suppression emojis/ponctuation |
| `generique_non_actionnable` | « ok », « bien », « top »… seul |

Les avis filtrés restent dans `fact_reviews` (traçabilité) mais sont exclus des marts métier.
Le filtre LLM (Ollama) est volontairement absent du MVP pour garder une stack légère ;
il s'ajoute facilement comme étape Python entre `refine_and_load` et `dbt_seed`.

---

## Catégorisation

**Étape 1 — heuristique (déterministe, rapide)**. Mots-clés FR/EN normalisés (NFD,
accent-stripped) avec gestion des négations (`pas une arnaque` ne déclenche pas
`transparence_financiere`). 8 catégories alignées sur les seeds dbt :

`app_fr` · `transparence_financiere` · `fiabilite_reservations` · `service_client` ·
`qualite_annonces` · `parcours_paiement` · `communication_hote` · `non_classe`

**Étape 2 — LLM Ollama (fallback uniquement)**. Sur les avis exploitables que
l'heuristique a laissés en `non_classe`, on demande à Ollama (modèle par défaut
`qwen2.5:3b`) de répondre par un JSON `{"category": "<code>", "confidence": <0-1>}`.
Tout output non parsable ou code invalide → la ligne reste `non_classe`. La colonne
`category_source` (`heuristic` / `llm`) trace l'origine et remonte dans
`fact_classifications.method` pour audit.

**Étape non-bloquante** : si Ollama est down ou désactivé (`OLLAMA_ENABLED=false`),
le DAG continue et toutes les lignes restent en classification heuristique.

4 catégories sont marquées `is_critical=true` (déclenchent un ticket si gravité haute) :
`transparence_financiere`, `fiabilite_reservations`, `service_client`, `parcours_paiement`.

---

## Sévérité

3 niveaux (`low` / `medium` / `high`). La règle combine :
- **score note** : `(5 − rating) / 4` ∈ [0,1]
- **score texte** : présence de mots-clés gravité (`arnaque`, `inadmissible`, `tribunal`…)

Override : note=1 OU 2+ mots-clés haute sévérité OU note=2 + catégorie critique → `high`.

---

## Intégrations externes

### Ollama (catégorisation LLM)

Deux modes au choix, sélectionnés via `OLLAMA_BASE_URL` dans `.env` :

**Mode A — Ollama sur le Mac hôte** (défaut, plus rapide, pas de RAM Docker)
```bash
# Sur le Mac, en dehors de Docker :
ollama serve              # démarre le serveur sur :11434
ollama pull qwen2.5:3b    # télécharge le modèle (≈ 2 GB)

# .env :
# OLLAMA_BASE_URL=http://host.docker.internal:11434
docker compose up -d --build
```

**Mode B — Ollama dans Docker** (portable, isolé, premier appel = pull lent)
```bash
# .env :
# OLLAMA_BASE_URL=http://ollama:11434
docker compose --profile with-ollama up -d --build
docker compose exec ollama ollama pull qwen2.5:3b
```

Désactiver complètement : `OLLAMA_ENABLED=false` dans `.env` → la tâche
`llm_classify` retourne immédiatement sans appeler Ollama.

### Notion (ticketing)

1. Crée une **integration** Notion (https://www.notion.so/profile/integrations) →
   récupère le `NOTION_TOKEN` (commence par `secret_`).
2. Crée une **database** Notion avec exactement ces propriétés :

| Propriété | Type Notion | Notes |
|---|---|---|
| `ticket_id` | Title | ex: `TICK-0001` |
| `review_id` | Number | clé d'idempotence — ne pas modifier manuellement |
| `brand` | Select | options : Abritel / Airbnb / Booking |
| `source` | Select | options : Trustpilot / Google Play / App Store |
| `category` | Select | libellé catégorie (cf. seeds) |
| `severity` | Select | options : high / medium / low |
| `rating` | Number | 1–5 |
| `status` | Select | options : open / in_progress / done (défaut : `open`) |
| `owner_team` | Select | options : sav / finance / produit / trust_safety |
| `occurred_at` | Date | date de l'avis |
| `excerpt` | Rich text | premiers ~280 caractères |

3. Partage la database avec ton intégration (menu `…` → `Add connections`).
4. Récupère le `NOTION_DATABASE_ID` (32 caractères dans l'URL de la DB).
5. Mets `NOTION_TOKEN` et `NOTION_DATABASE_ID` dans `.env`.

À chaque run, le DAG query la DB par `review_id` et ne crée que les tickets
manquants (idempotent — pas de doublons).

Si l'un des deux est vide, Notion est désactivé : seul `tickets.csv` est produit.

### Slack (notifications)

1. Crée une **incoming webhook** : https://api.slack.com/messaging/webhooks
2. Mets `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...` dans `.env`.

Le DAG envoie 1 message à la fin de chaque run avec un récap (nb tickets, nb
poussés vers Notion, nb alertes spike). Skip silencieux si rien à signaler ou
si la variable est vide.

---

## Visualisation

### Power BI (recommandé MVP — externe au compose)

Le compose n'embarque **pas** d'outil de visualisation. La doctrine est :
- Le DAG produit des marts SQL **propres** (étoile dim/fact + 4 `dm_*`).
- Power BI Desktop ou Service se connecte directement à Postgres et fait tout le rendu.

**Connexion** :

| Paramètre | Valeur |
|---|---|
| Hôte | `localhost` |
| Port | `5433` |
| Base | `voc` |
| User / Pwd | `postgres` / `postgres` |
| Schéma | `marts` |

**Tables suggérées par usage** :

| Audience | Mart consommable | Colonnes clé |
|---|---|---|
| Direction / CODIR | `dm_direction_synthese` | `total_reviews`, `avg_rating`, `share_critical`, `gap_vs_competitors` |
| Marketing | `dm_marketing_voc` | `review_count`, `avg_rating`, `share_high_severity`, `ratio_vs_abritel` |
| Finance | `dm_finance_litiges` | `vendor_responded`, `response_latency_days`, `severity_label` |
| SAV | `dm_sav_tickets` | `days_open`, `status_label`, `assignee` |

Pour des SQL plus libres (drill-down, agrégats custom), interroge directement les tables `fact_reviews`, `fact_classifications`, `fact_tickets` jointes aux `dim_*` (cf. `dbt/models/sources.yml` pour le schéma exact).

### Variantes BI embarquées (autres branches)

Si tu veux embarquer une stack BI dans le compose :
- **`git checkout dashboards-grafana`** — Grafana 11 + 3 dashboards JSON pré-construits (Executive Overview, Brand Comparison, Operations & SAV).
- **`git checkout dashboards-superset`** — Apache Superset 4.1 + datasource auto-provisionnée + 4 datasets (dashboards à créer dans l'UI).

### Autres outils (Power BI, Tableau, …)

Connexion directe **Postgres** depuis ta machine :

| Paramètre | Valeur (stack Docker → hôte) |
|---|---|
| Hôte | `localhost` |
| Port | `5433` |
| Base | `voc` |
| Schéma des marts | `marts` |

Tables : `dm_sav_tickets`, `dm_marketing_voc`, `dm_finance_litiges`, `dm_direction_synthese`.

---

## KPI portés par le MVP

Mesurés dans `dm_direction_synthese` (mis à jour à chaque run) :

| KPI | Définition | Source |
|---|---|---|
| **Time-to-detect** | Latence entre 1ʳᵉ plainte récurrente et alerte | `alerts.csv` (auto < 7j) |
| **Volume d'avis exploitables** | `total_reviews` (post quality filter) | `dm_direction_synthese` |
| **Note moyenne /5** | `avg_rating` par marque/jour | `dm_direction_synthese` |
| **% gravité haute** | `share_critical` | `dm_direction_synthese` |
| **Gap vs concurrents** | `gap_vs_competitors` (Abritel − moy. Airbnb/Booking) | `dm_direction_synthese` |

---

## Structure du repo

```
.
├── airflow/
│   ├── Dockerfile              # image Airflow custom (+ dbt-postgres + scrapers)
│   ├── requirements.txt
│   └── dags/voc_pipeline.py    # le DAG unique
│
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml            # cible : Postgres (`voc`)
│   ├── seeds/                  # 6 CSV (dimensions de référence)
│   └── models/
│       ├── sources.yml         # déclare raw.raw_reviews
│       ├── staging/            # nettoyage + dédup (vues)
│       ├── intermediate/       # résolution des FK (vues)
│       └── marts/
│           ├── core/           # dim_* + fact_* (tables)
│           └── consumption/    # 4 data marts métier (tables)
│
├── src/voc/                    # package Python
│   ├── config.py               # chemins, fenêtres, plafonds, intégrations, DSN Postgres
│   ├── ingestion/              # scrapers + runner
│   ├── refinement/             # quality_filter + categorize + llm_classify (Ollama)
│   ├── warehouse/loader.py     # bronze parquet → Postgres voc.raw.raw_reviews
│   └── activation/             # alerting + ticketing + notion + slack
│
├── db-init/                    # scripts SQL exécutés au premier démarrage Postgres
│   └── 01-create-voc-db.sql    # crée la DB voc (data warehouse)
│
├── data/                       # généré au runtime (gitignored sauf .gitkeep)
│   ├── bronze/                 # parquet brut par run
│   ├── alerts.csv
│   └── tickets.csv
│
├── tests/                      # pytest (quality_filter + categorize + ollama + notion + slack)
├── docker-compose.yml          # postgres + airflow (+ ollama optionnel)
├── pyproject.toml              # deps locales (dev hors Docker)
└── README.md
```

---

## Développement local (sans Docker)

```bash
uv sync --extra dev                                       # installe deps
uv run pytest                                              # tests (HTTP + DB mockés)
```

Pour exécuter une étape Python isolée en local (avec la stack Docker tournant) :
```bash
# Postgres tourne dans Docker, exposé sur localhost:5433.
export VOC_DATA_DIR=$(pwd)/data
export VOC_PG_HOST=localhost VOC_PG_PORT=5433
export VOC_PG_USER=postgres VOC_PG_PASSWORD=postgres VOC_PG_DBNAME=voc

uv run python -c "from voc.ingestion.runner import run; print(run())"
uv run python -c "from voc.warehouse.loader import load; print(load())"
cd dbt && uv run dbt seed --profiles-dir . && uv run dbt run --profiles-dir .
```

---

## Troubleshooting

| Symptôme | Cause probable | Fix |
|---|---|---|
| `airflow-init` échoue à `db migrate` | Volume Postgres pré-existant incompatible | `docker compose down -v` puis re-up |
| `Bind for 127.0.0.1:5432 failed: port is already allocated` | Postgres local déjà sur 5432 | Le compose mappe sur 5433 côté hôte ; si conflit aussi en 5433, modifier le mapping |
| DAG vide dans l'UI | Volume `./airflow/dags` mal monté | Vérifier `docker compose config` ; sur Windows, autoriser le partage du dossier dans Docker Desktop |
| `extract` retourne 0 avis Trustpilot | Challenge AWS WAF Trustpilot | Le pipeline continue avec GP + AS ; Playwright peut être ajouté pour bypasser (alourdit l'image) |
| `dbt run` : `relation "raw.raw_reviews" does not exist` | `refine_and_load` n'a pas tourné | Vérifier l'ordre des tâches (extract → refine_and_load → dbt_seed → dbt_run) |
| `database "voc" does not exist` | Volume Postgres préexistant qui n'a pas exécuté `db-init/` | `docker compose down -v` (efface aussi `airflow`, à utiliser avec précaution) |
| Marts vides en sortie | Tous les avis filtrés (`is_exploitable=false`) | Augmenter `VOC_SCRAPE_WINDOW_DAYS` ou inspecter `raw.raw_reviews.exclusion_reason` |

---

## Limites assumées du MVP

- **LLM en fallback seulement** (sur `non_classe`) — pas de re-classification globale.
  Pour passer en prod : appel LLM systématique avec cache, ou modèle plus puissant.
- **Tickets Notion en append-only avec idempotence par `review_id`** — le statut
  d'un ticket déjà créé n'est jamais re-synchronisé depuis le pipeline. Les équipes
  métier gèrent le cycle de vie côté Notion (open → in_progress → done).
- **Notifications Slack basiques** (1 message récap par run via webhook). Pas de
  threading par catégorie ni de mention d'équipes — facile à ajouter.
- **Pas d'incrémentalité fine** côté dbt (`table` plein rebuild) — les marts sont recréés à chaque `dbt run`.
  Acceptable au volume MVP (~1k avis/run). Pour scale : passer les facts en `incremental` dbt.
- **Trustpilot fragile** — sans Playwright, le scraper peut être bloqué par AWS WAF.
  Le circuit reste fonctionnel sur GP + AS si TP retourne 0.
