# Field Shift Togo — Backend

Réponse au défi NASA Space Apps 2026 *« Field Shift: Adapting Farms with NASA Data »* (hackathon des 14 et 15 novembre 2026).
Ce dépôt contient **uniquement le backend** : l'API FastAPI (`apps/api/`) et le pipeline de données NASA POWER (`pipeline/`). Le frontend (PWA hors ligne) est développé séparément.

- Spécification de référence : [`BACKEND_FIELD_SHIFT.md`](BACKEND_FIELD_SHIFT.md)
- Choix d'implémentation : [`apps/api/DECISIONS.md`](apps/api/DECISIONS.md)

> Les scénarios climatiques sont des **stress-tests hypothétiques, jamais des prévisions**.
> Les scores de rotation sont des **scores logiciels, pas des rendements**.
> Chaque donnée porte un `source_type` (`nasa_power`, `provisional_demo`, `synthetic_demo`, `synthetic_scenario`…).

## Principe

```
NASA POWER ──► pipeline/ (fetch → ET0 FAO-56 → décades → normales 1991-2020 → paquets)
                    │                                   │
                    ▼                                   ▼
          data/processed/ (+ BD)          packs/{zone}.json  (< 100 Ko, JSON canonique)
                                          packs/manifest.json · zone_pack.schema.json · golden_cases.json
                                                        │
FastAPI /api/v1 ── packs (ETag/304) · zones · moteur (simulate / rotation) · devices · sync · posts
```

Le téléphone garde les paquets en cache et calcule hors ligne avec un moteur TypeScript. Le moteur Python d'`apps/api/app/engine/` est le **moteur de référence** : il produit `packs/golden_cases.json`, que le moteur TS doit reproduire (tolérance 0,01 sur les nombres).

## Contrat avec le frontend

| Élément | Source de vérité |
|---|---|
| Format du paquet de zone (§7) | `apps/api/app/schemas/pack.py` (`ZonePack`) → `packs/zone_pack.schema.json` |
| Endpoints (§10) | `/api/v1/docs` (OpenAPI) quand l'API tourne |
| Cas de test du moteur (§9.6) | `packs/golden_cases.json` (39 cas, paquets embarqués) |

## Relancer tout de zéro (Windows / PowerShell, sans Docker)

```powershell
# depuis la racine du dépôt
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e "apps/api[dev]"

cd apps/api
python -m alembic upgrade head          # base SQLite locale apps/api/fieldshift.db
python -m app.cli seed                  # référentiels + 3 parcelles de démo (synthetic_demo)
cd ../..
python -m pipeline.run_all              # NASA POWER 1991-2025 → paquets (≈ 1 min au 1er appel, puis cache)
# python -m pipeline.run_all --offline  # sans réseau : climat FICTIF (synthetic_demo)
cd apps/api
python -m app.cli export-golden         # packs/golden_cases.json (à refaire après chaque build de paquets)
python -m app.cli seed                  # recharge climate_dekad + table packs (idempotent)
python -m pytest -q                     # tous les tests
python -m uvicorn app.main:app --reload # http://127.0.0.1:8000/api/v1/health , /api/v1/docs
```

Exemple d'appel (PowerShell) :

```powershell
$body = '{"zone_id":"kara_kara","soil_id":"sandy_loam","previous_crop_id":"sorghum","priority":"drought_resilience","scenario_id":"dry_minus20"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/rotation/recommend -ContentType "application/json" -Body $body
```

Postgres : copier `apps/api/.env.example` en `apps/api/.env` (URL `postgresql+asyncpg://…`).
Plan de secours démo : `python -m pipeline.build_packs --export-frontend` copie `packs/` vers `apps/web/public/packs/`.

## Docker (⚠️ non testé)

Docker n'est **pas installé** sur le poste de développement : `apps/api/Dockerfile` et `docker-compose.yml` ont été écrits **sans pouvoir être testés**. De même, l'API n'a été exécutée que sur **SQLite** ; les modèles n'utilisent que des types portables (`JSON`, `Uuid`, `DateTime(timezone=True)`), mais la compatibilité Postgres reste à vérifier.

```bash
docker compose up -d db          # Postgres seul
docker compose up --build        # Postgres + API (migrations + seed au démarrage) → http://localhost:8000/api/v1/health
```

L'image se construit depuis la racine (`docker build -f apps/api/Dockerfile .`) car elle embarque `data/`, `pipeline/` et `packs/`. Les paquets ne sont jamais générés à la volée : il faut les reconstruire puis redéployer.

## Structure

```
BACKEND_FIELD_SHIFT.md      spécification
data/                       pack de données provisoires (fichiers source inchangés)
  seed/                     référentiels enrichis (§8) : crops, zones, soils, rules, scenarios, scoring
  raw/power/                cache brut NASA POWER (généré, non versionné)
  processed/                décades par année + climatologies (généré)
schemas/ docs/ scripts/     reste du pack AGRI SHIFT (cas V001-V006, dictionnaire, script Open-Meteo de secours)
pipeline/                   fetch_power, et0, dekads, climatology, synthetic_fallback, build_packs, run_all
packs/                      paquets générés + manifest + JSON Schema + golden
apps/api/
  app/engine/               moteur de référence pur (dekad, rules, water_balance, rotation, explain)
  app/schemas/              Pydantic (pack.py = contrat)
  app/routers/              health, zones, packs, engine, devices, sync, posts
  app/services/             paquets, seed, sync, synthèse, golden, rate limit
  alembic/  tests/  Dockerfile  DECISIONS.md  .env.example
docker-compose.yml
```

## Endpoints (`/api/v1`)

| Méthode | Route | Auth |
|---|---|---|
| GET | `/health` | — |
| GET | `/zones`, `/zones/{zone_id}/summary`, `/crops`, `/scenarios`, `/soils` | — |
| GET | `/packs/manifest`, `/packs/{zone_id}` (ETag, 304) | — |
| POST | `/simulate`, `/rotation/recommend`, `/rotation/compare-scenarios` | — |
| POST | `/devices/register` | — |
| PATCH | `/devices/me` | `X-Device-Token` |
| POST / GET | `/sync/push`, `/sync/pull?since=` | `X-Device-Token` |
| GET / POST / DELETE | `/posts?zone_id=&before=&limit=`, `/posts`, `/posts/{id}` | POST/DELETE : `X-Device-Token` |

Erreurs : `{"error": {"code": "...", "message_fr": "..."}}`.

## Données

| Zone | Source climat | Paquet | ET0 moyenne | Pluie annuelle (normale 1991-2020) |
|---|---|---|---|---|
| maritime_lome | `nasa_power` | 12 388 octets | 3,92 mm/j | 1 057 mm |
| plateaux_kpalime | `nasa_power` | 12 396 octets | 3,89 mm/j | 1 223 mm |
| kara_kara | `nasa_power` | 12 226 octets | 4,68 mm/j | 1 148 mm |

NASA POWER est une **réanalyse sur une maille d'environ 50 km**, pas une mesure de parcelle. Les paramètres de cultures, de sols et de règles sont **provisoires**, à valider par un agronome.

## Travail préparatoire

Le règlement du hackathon (14 et 15 novembre 2026) impose de déclarer le code écrit avant l'événement.

| Date | Contenu |
|---|---|
| 2026-10-27 | Pack de données provisoires AGRI SHIFT (cultures, zones, règles, données synthétiques, script Open-Meteo), fourni par l'équipe. |
| 2026-11-04 | Spécification backend (`BACKEND_FIELD_SHIFT.md`). |
| 2026-11-04 | **P1** : squelette FastAPI (config, BD SQLAlchemy async, Alembic, `/health`, format d'erreur unique), données de référence enrichies `data/seed/*.json`, commande `seed` idempotente. |
| 2026-11-04 | **P2** : moteur de référence (décades, Kc, bilan hydrique décadaire, WRSI, périodes critiques, règles structurées sans `eval`, rotation, explications en français) et modèle `ZonePack`. |
| 2026-11-04 | **P3** : pipeline NASA POWER (téléchargement par tranches avec cache, ET0 FAO-56 Penman-Monteith, décades, normales/p20/CV, tendance 2016-2025, démarrage de saison), secours synthétique `--offline`, construction des paquets, manifest et JSON Schema. Données NASA POWER 1991-2025 téléchargées pour les 3 zones. |
| 2026-11-04 | **P4** : routes zones/référentiels, paquets (ETag/304, gzip), moteur en ligne (`/simulate`, `/rotation/*`), `export-golden` (39 cas). |
| 2026-11-04 | **P5** : identité d'appareil sans compte, synchronisation hors ligne (dernière écriture gagnante, idempotence, droits, pagination), plateforme d'échange (posts), synthèse publique de zone (seuil d'anonymat ≥ 3). |
| 2026-11-04 | **P6** : Dockerfile et docker-compose (non testés), README, `DECISIONS.md`, parcours de démo complet en local. |
