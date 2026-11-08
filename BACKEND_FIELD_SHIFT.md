# Field Shift Togo — Spécification backend (FastAPI + pipeline NASA)

> **Document destiné à un agent de code (Claude Opus 5.5) et au développeur backend.**
> Lis tout le document avant d'écrire du code. Implémente dans l'ordre des phases (§14).
> Code et identifiants en **anglais** ; textes destinés aux producteurs (explications, messages) en **français**.

---

## 0. Instructions pour l'agent

- Tu implémentes **uniquement le backend** : `apps/api/` (FastAPI) et `pipeline/` (Python, données NASA).
- Le frontend (PWA Next.js offline-first) est fait par une autre personne. **Ton contrat avec lui = le format du paquet de zone (§7) + les endpoints (§10) + le fichier golden (§9.6).** Ne change jamais ces formats sans le signaler explicitement.
- **N'invente aucune donnée observée.** Toute valeur non mesurée porte un `source_type` honnête (§4). Une valeur provisoire reste marquée `provisional_demo`.
- Si un point de cette spec est ambigu ou contradictoire, choisis l'option la plus simple, **note-la dans `apps/api/DECISIONS.md`** et continue.
- Ne rajoute pas de fonctionnalités hors périmètre (§15).
- Chaque phase se termine par des tests qui passent (`pytest`).

---

## 1. Le projet en 1 minute

**Field Shift Togo** répond au défi NASA Space Apps 2026 *« Field Shift: Adapting Farms with NASA Data »* (hackathon 14–15 nov. 2026).

- **Problème** : les producteurs togolais doivent adapter leurs cultures au changement climatique, souvent **sans internet**.
- **Solution** : un outil d'aide à la décision (pas un portail météo) qui :
  1. **compare des rotations de cultures** sur 2 à 4 saisons (moteur de règles + score) ;
  2. **simule** leur comportement sous des scénarios climatiques (pluie −20 %, +2 °C…) avec un **bilan hydrique explicable** (« stress en floraison car pluie −20 % ») ;
  3. s'appuie sur des **données NASA POWER** résumées par zone ;
  4. fonctionne **hors-ligne** sur téléphone.
- **Zones pilotes** : `maritime_lome`, `plateaux_kpalime`, `kara_kara`.
- **Cultures MVP** : maïs, sorgho, riz, arachide, niébé.

---

## 2. Principe d'architecture (le « pourquoi »)

1. **La donnée NASA n'est pas consultable hors-ligne.** On la télécharge **à l'avance** côté serveur, on l'agrège par **décade** et par zone, puis on produit un **paquet JSON autosuffisant par zone** (< 100 Ko) que le téléphone garde en cache.
2. **Le calcul se fait sur le téléphone** (moteur TypeScript côté frontend) à partir du paquet. Sinon : pas de recommandation en mode avion.
3. **Le backend Python fournit en plus un moteur de référence** (§9), identique fonctionnellement :
   - il sert d'**oracle de tests** : il génère `golden_cases.json` que le moteur TS doit reproduire ;
   - il expose des endpoints `/rotation` et `/simulate` utilisables en ligne (démo API, et frontend avant que son moteur TS soit prêt).
4. **Le backend reste mince** : servir les paquets, synchroniser les données des producteurs, porter la plateforme d'échange.

```
NASA POWER ──► pipeline/ (fetch → ET0 → décades → normales → packs)
                    │                         │
                    ▼                         ▼
             PostgreSQL (Supabase)     packs/{zone}.json + manifest.json
                    ▲                         │
                    └──── FastAPI  /api/v1 ───┘──► PWA (IndexedDB, calcul local)
                          packs · sync · posts · zones · rotation · simulate
```

---

## 3. Stack et conventions

| Élément | Choix |
|---|---|
| Langage | Python 3.11+ |
| API | FastAPI, Pydantic v2, Uvicorn |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic |
| Base | PostgreSQL (Supabase en prod, Docker en local) ; tests sur SQLite via `aiosqlite` → **éviter les types spécifiques Postgres** (utiliser `JSON`, pas `JSONB`; `Uuid` générique SQLAlchemy) |
| Données | pandas, numpy, httpx (avec retries) |
| Tests | pytest, pytest-asyncio, httpx `AsyncClient` |
| Qualité | ruff + mypy (non bloquant) |
| Config | `pydantic-settings`, fichier `.env` |

Conventions :
- Préfixe d'API : `/api/v1`.
- Dates en ISO 8601 UTC. Identifiants des entités du producteur : **UUID générés côté client**.
- Toutes les sorties numériques des moteurs arrondies à **2 décimales** au moment de la sérialisation (pas pendant le calcul).
- Réponses gzip (`GZipMiddleware`, `minimum_size=1000`). CORS ouvert sur l'origine du frontend (`FRONTEND_ORIGIN`).

---

## 4. Provenance des données (règle non négociable)

Chaque ligne de donnée, chaque paquet et chaque résultat porte un `source_type` :

| `source_type` | Sens | Badge attendu côté UI |
|---|---|---|
| `nasa_power` | Série NASA POWER (réanalyse/modèle, pas mesure de parcelle) | « Source : NASA POWER, période X, réanalyse » |
| `public_historical_reanalysis` | Autre réanalyse publique (Open-Meteo) — **secours uniquement** | idem avec la source |
| `provisional_demo` | Paramètre/règle provisoire à valider par un agronome | « Valeur provisoire » |
| `synthetic_demo` | Donnée inventée pour tests | « DONNÉES SYNTHÉTIQUES — TEST UNIQUEMENT » |
| `synthetic_scenario` | Scénario hypothétique, **jamais une prévision** | « Scénario hypothétique » |
| `computed` | Calculé par nos soins à partir de sources listées dans `derived_from` | — |

- Un résultat de moteur hérite du `source_type` « le plus faible » de ses entrées (ordre : `synthetic_demo` < `provisional_demo` < `computed`/`nasa_power`) et renvoie la liste complète dans `data_provenance`.
- Les scores de rotation sont des **scores logiciels**, pas des rendements. Chaque réponse du moteur contient `disclaimer_fr`.

---

## 5. Structure du dépôt (partie backend)

```
field-shift/
├─ data/                          # pack de données fourni (ne pas renommer les fichiers source)
│  ├─ cultures.json  regles_rotation.json  zones.json
│  ├─ synthetic/ climat_synthetique.json  parcelles_demo.json  scenarios.json
│  ├─ seed/                       # NOUVEAU : versions enrichies (§8)
│  │  ├─ crops.json  rules.json  zones.json  soils.json  scenarios.json  scoring.json
│  ├─ raw/power/{zone_id}.csv     # cache brut NASA (généré)
│  └─ processed/                  # décades, normales (généré)
├─ pipeline/
│  ├─ __init__.py
│  ├─ config.py                   # zones, périodes, chemins
│  ├─ fetch_power.py
│  ├─ et0.py                      # FAO-56 Penman-Monteith journalier
│  ├─ dekads.py                   # jour → décade, agrégation
│  ├─ climatology.py              # normales, variabilité, tendance, démarrage saison
│  ├─ build_packs.py
│  ├─ synthetic_fallback.py       # génère un climat synthétique si réseau absent
│  └─ run_all.py
├─ packs/                         # généré : {zone_id}.json + manifest.json
└─ apps/api/
   ├─ app/
   │  ├─ main.py  config.py  db.py  deps.py
   │  ├─ models/                  # SQLAlchemy
   │  ├─ schemas/                 # Pydantic (dont pack.py = contrat)
   │  ├─ routers/ health.py zones.py packs.py devices.py sync.py posts.py engine.py
   │  ├─ engine/                  # moteur de référence (§9)
   │  │  ├─ dekad.py  rules.py  water_balance.py  rotation.py  explain.py
   │  ├─ services/ pack_service.py  sync_service.py  summary_service.py
   │  └─ cli.py                   # seed, build-packs, export-golden
   ├─ alembic/
   ├─ tests/
   ├─ DECISIONS.md
   ├─ Dockerfile  pyproject.toml  .env.example
└─ docker-compose.yml             # postgres + api
```

---

## 6. Pipeline de données NASA (`pipeline/`)

### 6.1 `fetch_power.py`
- API : `GET https://power.larc.nasa.gov/api/temporal/daily/point`
- Paramètres de requête :
  - `parameters=T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,WS2M,ALLSKY_SFC_SW_DWN`
  - `community=AG`, `latitude`, `longitude`, `start=YYYYMMDD`, `end=YYYYMMDD`, `format=JSON`
- Période : **1991-01-01 → 2025-12-31** (normale 1991–2020 + années récentes pour la tendance).
- Découper en tranches de **10 ans** par requête ; timeout 120 s ; 3 retries avec backoff exponentiel ; pause 1 s entre requêtes.
- Lecture : `properties.parameter.{PARAM}.{YYYYMMDD}`. La valeur de remplissage (lue dans `header.fill_value`, typiquement `-999`) → `NaN`.
- **Unités** : les lire dans la réponse (`parameters.{PARAM}.units`). Le rayonnement doit être en **MJ/m²/jour** ; s'il arrive en kWh/m²/jour, multiplier par 3,6. Lever une erreur claire si une unité inattendue apparaît.
- Récupérer l'**altitude** renvoyée (`geometry.coordinates[2]`) et la stocker par zone (nécessaire à l'ET0).
- Écrire `data/raw/power/{zone_id}.csv` (colonnes : `date,t2m,t2m_max,t2m_min,precip_mm,rh2m,ws2m,rs_mj,elevation_m`) + `data/raw/power/{zone_id}.meta.json` (URLs, date de téléchargement, unités, fill_value).
- **Idempotent** : ne retélécharge pas une tranche déjà présente sauf `--force`.
- CLI : `python -m pipeline.fetch_power --zone all|<zone_id> --start 1991-01-01 --end 2025-12-31 [--force]`

### 6.2 `et0.py` — ET0 FAO-56 Penman-Monteith (journalier)
Implémenter la formule FAO-56 (éq. 6) avec :
- pression `P = 101.3 × ((293 − 0.0065 z)/293)^5.26`, `γ = 0.000665 P`
- `es = (e°(Tmax) + e°(Tmin))/2`, `e°(T) = 0.6108 exp(17.27 T/(T+237.3))`
- `ea = RH2M/100 × es` (RH moyenne : simplification à noter dans `DECISIONS.md`)
- `Δ` à partir de `T2M` (moyenne)
- `Ra` à partir de la latitude et du jour de l'année (éq. 21), `Rso = (0.75 + 2e-5 z) Ra`
- `Rns = 0.77 Rs`, `Rnl` (éq. 39, σ = 4.903e-9, Tmax/Tmin en K, ratio `Rs/Rso` borné à [0.25, 1])
- `G = 0` (pas de temps journalier), `u2 = WS2M`
- Résultat borné ≥ 0.

Tests :
- fonctions intermédiaires (`e°(25) ≈ 3.168 kPa`, `Δ(25) ≈ 0.189 kPa/°C`) ;
- cohérence : sur les données réelles des 3 zones, **moyenne annuelle d'ET0 entre 3 et 7 mm/j**, aucune valeur négative ou NaN hors jours manquants.

### 6.3 `dekads.py`
- Décade : jours 1–10 → D1, 11–20 → D2, 21–fin → D3. Index annuel `dekad = (mois−1)×3 + d`, de **1 à 36**.
- Agrégation par (zone, année, décade) : `p_mm = somme`, `et0_mm = somme`, `tmean_c = moyenne`, `tmax_c = moyenne`, `n_days`, `n_missing`.
- Décade invalide si `n_missing > 3` → valeurs `null`.
- Sortie : `data/processed/dekad_{zone_id}.csv` + table `climate_dekad` (§8.1).
- Fournir aussi `dekad_label_fr(dekad) -> "juil. D2"` (abréviations : janv., févr., mars, avr., mai, juin, juil., août, sept., oct., nov., déc.).

### 6.4 `climatology.py`
Pour chaque zone et chaque décade (1..36), sur **1991–2020** :
- `p_mm` (moyenne), `et0_mm` (moyenne), `tmean_c` (moyenne)
- `p_p20` (20ᵉ centile = « année sèche »), `p_cv` (écart-type/moyenne, `null` si moyenne < 1 mm)

Tendance (bloc `trend`) : période récente **2016–2025** vs normale **1991–2020** :
- `p_change_pct` (cumul annuel), `t_change_c` (moyenne annuelle), `recent_period`, `baseline_period`.
- C'est un **constat historique**, jamais une prévision.

Démarrage de saison (`onset_dekad_clim`) — méthode simplifiée à documenter :
- Dans la fenêtre de recherche de la saison (`search_from`..`search_to`, §8.3), première décade où `p_mm ≥ 25` **et** la somme des 2 décades suivantes `≥ 20`.
- Si aucune décade ne satisfait : `null` → on garde la date provisoire.

### 6.5 `build_packs.py`
- Lit `data/seed/*.json` + `data/processed/*`.
- Écrit `packs/{zone_id}.json` (schéma exact §7), valide avec le modèle Pydantic `ZonePack`.
- Calcule `sha256` du JSON canonique (clés triées, `separators=(",", ":")`, UTF-8).
- Écrit `packs/manifest.json` : `[{zone_id, pack_version, sha256, size_bytes, generated_at}]`.
- `pack_version` = `YYYY.MM.DD-N` (N incrémenté si plusieurs builds le même jour).
- Option `--export-frontend <chemin>` : copie `packs/` vers `apps/web/public/packs/` (plan de secours démo).

### 6.6 `synthetic_fallback.py`
Si NASA POWER est injoignable (démo sans réseau, CI) : générer un climat décadaire **plausible mais fictif** par zone (profil unimodal pour Kara, bimodal pour Maritime/Plateaux), seed aléatoire fixe, **`source_type: "synthetic_demo"`** partout. `build_packs` doit fonctionner avec cette source.

### 6.7 `run_all.py`
`python -m pipeline.run_all [--offline]` : fetch → et0 → dekads → climatology → build_packs. `--offline` = fallback synthétique.

---

## 7. Contrat : format du paquet de zone (`packs/{zone_id}.json`)

**C'est l'interface partagée avec le frontend. Le modèle Pydantic `ZonePack` (`app/schemas/pack.py`) est la source de vérité ; exporter aussi son JSON Schema dans `packs/zone_pack.schema.json`.**

```json
{
  "schema_version": 1,
  "pack_version": "2026.11.05-1",
  "generated_at": "2026-11-05T10:00:00Z",
  "zone": {
    "zone_id": "kara_kara",
    "name_fr": "Kara",
    "region": "Kara",
    "latitude": 9.5511,
    "longitude": 1.1861,
    "elevation_m": 340,
    "seasons": [
      {
        "season_id": "main",
        "label_fr": "Saison des pluies",
        "sowing_dekad": 16,
        "sowing_source": "computed",
        "provisional_sowing_dekad": 16,
        "onset_dekad_clim": 16
      }
    ],
    "coordinate_note": "Point de référence approximatif; pas une parcelle agricole."
  },
  "climate": {
    "source_type": "nasa_power",
    "source_name": "NASA POWER daily point (community AG)",
    "baseline_period": "1991-2020",
    "units": { "p_mm": "mm/décade", "et0_mm": "mm/décade", "tmean_c": "°C" },
    "dekads": [
      { "dekad": 1, "label_fr": "janv. D1", "p_mm": 0.4, "p_p20": 0.0, "p_cv": null, "et0_mm": 52.1, "tmean_c": 27.8 }
    ],
    "trend": {
      "baseline_period": "1991-2020",
      "recent_period": "2016-2025",
      "p_change_pct": -6.0,
      "t_change_c": 0.7,
      "note_fr": "Constat historique, pas une prévision."
    },
    "warnings_fr": ["Réanalyse sur une maille de ~50 km : pas une mesure de votre champ."]
  },
  "crops": [ "… §8.2 …" ],
  "soils": [ "… §8.4 …" ],
  "rules": [ "… §8.5 …" ],
  "scenarios": [ "… §8.6 …" ],
  "scoring": { "… §8.7 …" },
  "data_provenance": [
    { "item": "climate", "source_type": "nasa_power" },
    { "item": "crops", "source_type": "provisional_demo" },
    { "item": "rules", "source_type": "provisional_demo" },
    { "item": "scenarios", "source_type": "synthetic_scenario" }
  ]
}
```

Exigences :
- Exactement **36 décades**, triées.
- Taille < 100 Ko non compressé.
- Aucun champ supprimé ou renommé sans incrémenter `schema_version`.

---

## 8. Données de référence enrichies (`data/seed/`)

Créer ces fichiers à partir du pack existant. **Toutes les valeurs ajoutées sont `provisional_demo`**, avec `source_note` (« ordre de grandeur inspiré de FAO-56, à valider par un agronome »).

### 8.1 Table `climate_dekad`
`zone_id, year, dekad, p_mm, et0_mm, tmean_c, tmax_c, n_days, n_missing, source_type` — clé (zone_id, year, dekad).

### 8.2 `crops.json`
Normaliser les noms de champs du pack (`water_need_class_demo` → `water_need`, etc.) et ajouter les paramètres du bilan hydrique :

| crop_id | name_fr | family | n_fixing | cycle_days | water_need | drought_tolerance | food_staple | kc_ini | kc_mid | kc_end | root_depth_m | depletion_p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| maize | Maïs | Poaceae | false | 100 | medium_high | low_medium | true | 0.30 | 1.20 | 0.60 | 1.0 | 0.55 |
| sorghum | Sorgho | Poaceae | false | 110 | medium | high | true | 0.30 | 1.05 | 0.55 | 1.0 | 0.55 |
| rice | Riz | Poaceae | false | 120 | high | low | true | 1.05 | 1.20 | 0.75 | 0.5 | 0.20 |
| groundnut | Arachide | Fabaceae | true | 95 | medium | medium | false | 0.40 | 1.15 | 0.60 | 0.5 | 0.50 |
| cowpea | Niébé | Fabaceae | true | 75 | low_medium | medium_high | true | 0.40 | 1.05 | 0.60 | 0.6 | 0.45 |

Pour toutes les cultures, ajouter `phases` (fractions du cycle, somme = 1) :
`{"initial": 0.20, "development": 0.30, "mid": 0.30, "late": 0.20}` — la phase `mid` = **floraison/remplissage** (phase critique).

Champs communs : `source_type: "provisional_demo"`, `source_note`.

### 8.3 `zones.json` (saisons)
| zone_id | name_fr | saison | provisional_sowing_dekad | fenêtre onset (search_from–search_to) |
|---|---|---|---|---|
| maritime_lome | Maritime | `main` « Grande saison » | 10 (avr. D1) | 8–14 |
| maritime_lome | Maritime | `second` « Petite saison » | 25 (sept. D1) | 24–28 |
| plateaux_kpalime | Plateaux | `main` | 11 (avr. D2) | 8–15 |
| plateaux_kpalime | Plateaux | `second` | 25 | 24–28 |
| kara_kara | Kara | `main` « Saison des pluies » | 16 (juin D1) | 13–19 |

Règle dans `build_packs` : `sowing_dekad = onset_dekad_clim` s'il existe (et `sowing_source = "computed"`), sinon la valeur provisoire (`sowing_source = "provisional_demo"`).

### 8.4 `soils.json`
| soil_id | label_fr | taw_mm_per_m |
|---|---|---|
| sandy | Sableux | 70 |
| sandy_loam | Sablo-limoneux | 110 |
| loam | Limoneux | 140 |
| clay | Argileux | 170 |

### 8.5 `rules.json` — **format structuré (remplace les conditions en texte)**
Raison : la règle R003 actuelle (`scenario == 'dry'`) ne se déclenche jamais (les ids sont `dry_minus20`, `dry_hot`) et évaluer du texte est dangereux. **Aucun `eval`.**

```json
{
  "rule_id": "R003",
  "effect": "penalty",
  "delta": -10,
  "all": [
    { "field": "next.water_need", "op": "eq", "value": "high" },
    { "field": "scenario.rainfall_change_pct", "op": "lt", "value": 0 }
  ],
  "explanation_fr": "Culture très gourmande en eau dans un scénario plus sec.",
  "source_type": "provisional_demo"
}
```

- Contexte d'évaluation : `prev` (culture précédente), `next` (culture candidate), `scenario`.
- Champs accessibles : tout attribut de culture (`family`, `n_fixing`, `water_need`, `drought_tolerance`, `food_staple`…) et de scénario.
- Opérateurs : `eq`, `neq`, `lt`, `lte`, `gt`, `gte`, `in`, `eq_field` (compare à un autre champ : `{"field":"prev.family","op":"eq_field","value":"next.family"}`).
- `all` = ET logique. Si `prev` est absent (pas d'historique), toute condition portant sur `prev.*` est fausse.

Règles du MVP :
| rule_id | conditions | delta | explication |
|---|---|---|---|
| R001 | prev.family = Fabaceae ET next.family = Poaceae | +10 | Une légumineuse avant une céréale enrichit le sol en azote. |
| R002 | prev.family `eq_field` next.family | −5 | Même famille deux saisons de suite : plus de ravageurs et sol appauvri. |
| R003 | next.water_need = high ET scenario.rainfall_change_pct < 0 | −10 | Culture très gourmande en eau dans un scénario plus sec. |
| R004 | prev.family = Poaceae ET next.family = Fabaceae | +5 | Une légumineuse après une céréale aide le sol à se reconstituer. |

### 8.6 `scenarios.json`
Reprendre `baseline`, `dry_minus20`, `hot_plus2`, `dry_hot` du pack + ajouter `dry_minus10`, `dry_minus30`, `hot_plus1`. Champs : `scenario_id, label_fr, rainfall_change_pct, temperature_change_c, source_type: "synthetic_scenario", note_fr: "Stress-test hypothétique, pas une prévision."`

### 8.7 `scoring.json`
```json
{
  "season_resilience_base": { "food_security": 20, "drought_resilience": 30, "balanced": 25 },
  "priority_bonus": {
    "food_security": { "food_staple": 5, "drought_level_factor": 0 },
    "drought_resilience": { "food_staple": 0, "drought_level_factor": 2 },
    "balanced": { "food_staple": 2.5, "drought_level_factor": 1 }
  },
  "drought_levels": { "low": 0, "low_medium": 1, "medium": 2, "medium_high": 3, "high": 4 },
  "phase_weights": { "initial": 0.5, "development": 1.0, "mid": 2.0, "late": 0.5 },
  "et0_temp_sensitivity_per_c": 0.03,
  "initial_soil_water_fraction": 0.5,
  "horizon_default": 3,
  "horizon_max": 4,
  "top_n": 3,
  "source_type": "provisional_demo"
}
```

---

## 9. Moteur de référence (`app/engine/`) — doit être pur et déterministe

Fonctions pures, **sans accès BD ni réseau**, entrée = un `ZonePack` (objet Pydantic) + paramètres. Le frontend réimplémente exactement la même logique en TypeScript.

### 9.1 Utilitaires décades
- Les décades « bouclent » : après 36 vient 1.
- Nombre de décades d'un cycle : `n = ceil(cycle_days / 10)`.
- Phase de la décade `i` (0-indexée) : `f = (i + 0.5) / n`, comparée aux bornes cumulées de `phases` (initial, development, mid, late).

### 9.2 Kc par décade (courbe FAO simplifiée)
- `initial` : `kc_ini`
- `development` : interpolation linéaire `kc_ini → kc_mid` selon la position dans la phase
- `mid` : `kc_mid`
- `late` : interpolation linéaire `kc_mid → kc_end`

### 9.3 Bilan hydrique — `simulate(pack, crop_id, soil_id, scenario_id, sowing_dekad)`
```
TAW   = soil.taw_mm_per_m × crop.root_depth_m
SW    = initial_soil_water_fraction × TAW
seuil = (1 − crop.depletion_p) × TAW
pour chaque décade i du cycle (d = sowing_dekad + i, bouclé) :
    P    = climate[d].p_mm × (1 + scenario.rainfall_change_pct / 100)
    ETc  = Kc(i) × climate[d].et0_mm × (1 + et0_temp_sensitivity_per_c × scenario.temperature_change_c)
    Ks   = 1                si SW ≥ seuil
         = SW / seuil       sinon         (borné [0,1])
    ETa  = Ks × ETc
    SW   = clamp(SW + P − ETa, 0, TAW)
    stress_i = 1 − Ks
stress_index = Σ(w_phase(i) × stress_i) / Σ(w_phase(i))
wrsi         = 100 × Σ ETa / Σ ETc        (indice de satisfaction des besoins en eau, style FAO/FEWS NET)
```
Sortie `SimulationResult` :
```json
{
  "crop_id": "maize", "soil_id": "sandy_loam", "scenario_id": "dry_minus20",
  "sowing_dekad": 16, "harvest_dekad": 25,
  "stress_index": 0.31, "wrsi": 78.4,
  "dekads": [
    { "dekad": 16, "label_fr": "juin D1", "phase": "initial", "kc": 0.30,
      "p_mm": 41.2, "etc_mm": 14.1, "eta_mm": 14.1, "soil_water_mm": 62.0, "ks": 1.0, "stress": 0.0 }
  ],
  "critical_periods": [ { "from_label_fr": "août D1", "to_label_fr": "août D3", "phase": "mid", "mean_stress": 0.46 } ],
  "explanations_fr": [ "…" ],
  "assumptions_fr": [ "…" ],
  "source_type": "provisional_demo",
  "data_provenance": [ "…" ],
  "disclaimer_fr": "Simulation simplifiée à but d'aide à la réflexion ; ce n'est ni une prévision ni une estimation de rendement."
}
```
`critical_periods` = suites de décades consécutives avec `stress > 0.2`.

### 9.4 Explications (`explain.py`) — gabarits en français
- Scénario : « Scénario hypothétique : pluie {±x} %, température {+y} °C. »
- Stress critique : « {Culture} : manque d'eau en {phase_fr} ({from} → {to}), stress moyen {s}. »
  `phase_fr` : initial → « levée », development → « croissance », mid → « floraison/remplissage », late → « maturation ».
- Bilan : « Besoins en eau couverts à {wrsi} %. »
- Aucun stress : « Pas de manque d'eau marqué sur le cycle dans ce scénario. »
- Hypothèses (`assumptions_fr`) toujours listées : climat moyen 1991–2020, sensibilité ET0 de 3 %/°C, réserve du sol, pas de ruissellement, paramètres provisoires.

### 9.5 Rotation — `recommend(pack, plot, priority, scenario_id, horizon)`
Entrées : `plot = {zone_id, soil_id, previous_crop_id | null}`, `priority ∈ {food_security, drought_resilience, balanced}`, `horizon ∈ [2, horizon_max]`.

1. **Saisons** : la saison `k` (0-indexée) utilise `zone.seasons[k % len(seasons)]` (bimodal = alternance grande/petite saison ; Kara = une saison par an).
2. **Génération** : toutes les séquences de longueur `horizon` sur les cultures du paquet (5³ = 125, 5⁴ = 625).
3. Pour chaque saison `k` de la séquence, culture `c`, précédente `p` (`previous_crop_id` pour k = 0) :
   - `rule_pts` = somme des `delta` des règles qui matchent, avec la liste `{rule_id, delta, explanation_fr}`
   - `sim` = `simulate(c, soil, scenario, season.sowing_dekad)` (**mémoïser** par (c, soil, scenario, sowing_dekad))
   - `resilience_pts = season_resilience_base[priority] × (1 − sim.stress_index)`
   - `priority_pts = food_staple_bonus × [c.food_staple] + drought_level_factor × drought_levels[c.drought_tolerance]`
   - `season_score = rule_pts + resilience_pts + priority_pts`
4. `total_score = Σ season_score`.
5. Tri : `total_score` décroissant, puis `mean_stress` croissant, puis séquence par ordre alphabétique (déterminisme).
6. Renvoyer les `top_n` avec le détail par saison, les règles déclenchées, un résumé de simulation par saison (`stress_index`, `wrsi`, `critical_periods`, `explanations_fr`), `source_type`, `data_provenance`, `disclaimer_fr` (« Score logiciel de comparaison, pas un rendement estimé. »).

### 9.6 Fichier golden (contrat de tests avec le frontend)
`python -m app.cli export-golden` produit `packs/golden_cases.json` :
- le paquet `kara_kara` utilisé (ou son `sha256`) ;
- ~30 cas : `simulate` (5 cultures × 2 sols × 3 scénarios) + `recommend` (3 parcelles démo × 2 scénarios) + les cas V001–V003 ;
- pour chaque cas : `input` et `expected_output` complet.
Le moteur TS doit reproduire chaque sortie (tolérance 0,01 sur les nombres, égalité stricte sur l'ordre du classement et les `rule_id`).

### 9.7 Tests obligatoires du moteur (`tests/test_engine.py`)
- **V001** groundnut → maize, baseline : R001 appliquée (+10), disclaimer présent.
- **V002** maize → sorghum, baseline : R002 appliquée (−5).
- **V003** maize → rice, `dry_minus20` : R002 **et** R003 appliquées, chaque explication renvoyée.
- **V004** kara_kara + `dry_minus20` : le résultat porte `source_type` du scénario `synthetic_scenario` dans `data_provenance` et une mention « hypothétique ».
- **V005/V006** : un paquet construit en `--offline` porte `synthetic_demo` ; un paquet NASA porte `nasa_power` + `warnings_fr` non vide.
- Monotonie : pour une même culture, `stress_index(dry_minus30) ≥ stress_index(dry_minus10) ≥ stress_index(baseline)` ; `stress_index(hot_plus2) ≥ stress_index(baseline)`.
- Bornes : `0 ≤ stress_index ≤ 1`, `0 ≤ wrsi ≤ 100`, `0 ≤ soil_water ≤ TAW`.
- Déterminisme : deux appels identiques → sorties identiques.
- Aucune règle n'utilise `eval`/`exec` (test qui inspecte le module).

---

## 10. API FastAPI (`/api/v1`)

### 10.1 Santé et référentiels
| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | `{status, db, packs_count, version}` |
| GET | `/zones` | liste des zones (id, nom, région, coordonnées, saisons) |
| GET | `/zones/{zone_id}/summary` | synthèse publique (§10.5) |
| GET | `/crops`, `/scenarios`, `/soils` | référentiels (même contenu que dans les paquets) |

### 10.2 Paquets
| Méthode | Route | Description |
|---|---|---|
| GET | `/packs/manifest` | `[{zone_id, pack_version, sha256, size_bytes, url}]` |
| GET | `/packs/{zone_id}` | le paquet JSON ; en-tête `ETag: "<sha256>"` ; si `If-None-Match` correspond → **304** ; `Cache-Control: public, max-age=3600` |

Les paquets sont lus depuis le dossier `packs/` (chemin `PACKS_DIR`) et indexés au démarrage. Pas de génération à la volée.

### 10.3 Appareils (identité sans compte, compatible hors-ligne)
Pourquoi : une connexion Supabase Auth exige internet à la première ouverture ; sur le terrain c'est bloquant.
| Méthode | Route | Description |
|---|---|---|
| POST | `/devices/register` | body `{device_id (uuid client), display_name?, zone_id?, priority?}` → `{device_id, device_token}` (token aléatoire 32 octets, **stocké haché** sha256) |
| PATCH | `/devices/me` | mise à jour du profil |

Les routes protégées exigent l'en-tête `X-Device-Token`. Rate limit simple en mémoire (ex. 60 req/min/appareil).

### 10.4 Synchronisation (offline-first, « le local fait foi »)
Entités synchronisées : `plots`, `plot_seasons`, `posts`.
Chaque ligne porte : `id (uuid client)`, `updated_at` (horloge client), `deleted` (bool, suppression logique), et côté serveur `server_updated_at` (horloge serveur).

`POST /sync/push` (auth)
```json
{
  "changes": {
    "plots": [ { "id": "…", "zone_id": "kara_kara", "name": "Champ nord", "area_ha": 1.5, "soil_id": "sandy_loam", "updated_at": "…", "deleted": false } ],
    "plot_seasons": [ { "id": "…", "plot_id": "…", "season_label": "2026-main", "crop_id": "sorghum", "sowing_date": "2026-06-05", "yield_note": "…", "losses_note": "…", "updated_at": "…", "deleted": false } ],
    "posts": [ { "id": "…", "zone_id": "kara_kara", "body": "…", "updated_at": "…", "deleted": false } ]
  }
}
```
Règles :
- Upsert si la ligne n'existe pas ou si `incoming.updated_at > existing.updated_at` (**last-write-wins**). Sinon : `rejected` avec la version serveur.
- Un appareil ne peut modifier que ses propres lignes (sinon `rejected: forbidden`).
- Validation : `crop_id`, `soil_id`, `zone_id` existants ; `body` ≤ 1000 caractères ; `area_ha` 0 < x ≤ 100.
- Réponse : `{accepted: [ids], rejected: [{id, reason, server_row?}], server_time}`.
- Idempotent : rejouer le même push ne crée pas de doublon.

`GET /sync/pull?since=<server_time>` (auth)
- Renvoie les lignes **de l'appareil** (`plots`, `plot_seasons`, `posts`) + les **posts publics de sa zone**, avec `server_updated_at > since`.
- Réponse : `{changes: {…}, server_time}` ; le client garde `server_time` comme prochain curseur. Pagination si > 500 lignes (`next_since`).
- Pourquoi un curseur serveur : l'horloge des téléphones peut être fausse.

### 10.5 Synthèse publique de zone (page « Générale »)
`GET /zones/{zone_id}/summary`
- Climat : normales clés + `trend` (depuis le paquet).
- Agrégats **anonymes** des producteurs : répartition des cultures déclarées par saison (`season_label`), nombre de parcelles.
- **Seuil d'anonymat** : n'afficher une culture que si ≥ 3 parcelles distinctes ; sinon regrouper en « autres ».
- Derniers posts publics (20).

### 10.6 Plateforme d'échange
| Méthode | Route | Description |
|---|---|---|
| GET | `/posts?zone_id=&before=&limit=20` | posts publics d'une zone, pagination par date |
| POST | `/posts` | (auth) crée un post (même validation que la sync) |
| DELETE | `/posts/{id}` | (auth, auteur) suppression logique |

### 10.7 Moteur en ligne (démo API + secours frontend)
| Méthode | Route | Body | Réponse |
|---|---|---|---|
| POST | `/simulate` | `{zone_id, crop_id, soil_id, scenario_id, sowing_dekad?}` | `SimulationResult` (§9.3) |
| POST | `/rotation/recommend` | `{zone_id, soil_id, previous_crop_id?, priority, scenario_id, horizon?}` | top N (§9.5) |
| POST | `/rotation/compare-scenarios` | même body sans `scenario_id` + `scenario_ids[]` | pour chaque scénario, le top N → alimente les courbes « scénarios » de l'UI |

Ces routes chargent le paquet de la zone en mémoire et appellent le moteur de référence. Elles ne nécessitent pas d'auth.

### 10.8 Erreurs
Format unique : `{ "error": { "code": "unknown_crop", "message_fr": "Culture inconnue : xyz" } }`, codes HTTP cohérents (400/401/403/404/409/422/429).

---

## 11. Modèle de données (SQLAlchemy)

```
zones(zone_id PK, name_fr, region, latitude, longitude, elevation_m, seasons JSON, source_type)
crops(crop_id PK, name_fr, family, n_fixing, cycle_days, water_need, drought_tolerance,
      food_staple, kc_ini, kc_mid, kc_end, root_depth_m, depletion_p, phases JSON, source_type, source_note)
soils(soil_id PK, label_fr, taw_mm_per_m, source_type)
rotation_rules(rule_id PK, effect, delta, conditions JSON, explanation_fr, source_type)
scenarios(scenario_id PK, label_fr, rainfall_change_pct, temperature_change_c, source_type, note_fr)
climate_dekad(zone_id FK, year, dekad, p_mm, et0_mm, tmean_c, tmax_c, n_days, n_missing, source_type,
              PK(zone_id, year, dekad))
packs(zone_id FK, pack_version, sha256, size_bytes, generated_at, PK(zone_id, pack_version))
devices(device_id PK uuid, token_hash, display_name, zone_id FK?, priority, created_at, last_seen_at)
plots(id PK uuid, device_id FK, zone_id FK, name, area_ha, soil_id FK,
      updated_at, server_updated_at, deleted)
plot_seasons(id PK uuid, plot_id FK, device_id FK, season_label, crop_id FK, sowing_date,
             yield_note, losses_note, updated_at, server_updated_at, deleted)
posts(id PK uuid, device_id FK, zone_id FK, body, updated_at, server_updated_at, deleted)
```
Index : `server_updated_at` sur les 3 tables synchronisées ; `(zone_id, server_updated_at)` sur `posts`.

`python -m app.cli seed` : charge `data/seed/*.json` dans la base (idempotent, upsert) + 3 appareils/parcelles de démo issus de `data/synthetic/parcelles_demo.json` (marqués `synthetic_demo`).

---

## 12. Configuration (`.env.example`)
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/fieldshift
PACKS_DIR=../../packs
DATA_DIR=../../data
FRONTEND_ORIGIN=http://localhost:3000
RATE_LIMIT_PER_MIN=60
LOG_LEVEL=info
```

## 13. Exécution
```
docker compose up -d db
cd apps/api && pip install -e ".[dev]"
alembic upgrade head
python -m app.cli seed
python -m pipeline.run_all            # ou --offline sans réseau
python -m app.cli export-golden
uvicorn app.main:app --reload
pytest -q
```
Déploiement : API sur Render/Railway (Dockerfile), base Supabase (Postgres), paquets copiés dans le frontend en secours (`build_packs --export-frontend`).

---

## 14. Ordre d'implémentation et critères de fin

| Phase | Contenu | Terminé quand |
|---|---|---|
| **P1** | Squelette FastAPI, config, BD, Alembic, `/health`, `data/seed/*.json`, `cli seed` | `pytest` vert, `/health` OK |
| **P2** | Moteur de référence (§9) + tests V001–V006 + monotonie/bornes | tous les tests moteur verts |
| **P3** | Pipeline : `fetch_power`, `et0`, `dekads`, `climatology`, `synthetic_fallback`, `build_packs` | 3 paquets valides (schéma Pydantic), < 100 Ko, manifest OK, en ligne **et** `--offline` |
| **P4** | Routes `/zones`, `/crops`, `/packs/*` (ETag/304), `/simulate`, `/rotation/*` + `export-golden` | golden généré, tests d'API verts |
| **P5** | `/devices`, `/sync/push`, `/sync/pull`, `/posts`, `/zones/{id}/summary` | tests : LWW, idempotence, droits, anonymat ≥ 3 |
| **P6** | Dockerfile, README backend, `DECISIONS.md`, données de démo | `docker compose up` + parcours complet OK |

Priorité absolue si le temps manque : **P1 → P2 → P3 → P4**. La sync (P5) peut être réduite au strict minimum (`push`/`pull` des parcelles).

---

## 15. Hors périmètre (ne pas implémenter maintenant)
- GPM IMERG, SMAP, MODIS/VIIRS NDVI, Landsat (prévoir seulement un registre de sources extensible dans `pipeline/config.py`).
- Prévisions météo (le frontend appelle directement un service de prévision et l'étiquette comme tel).
- SMS / USSD / vocal, langues locales, réseau Wi-Fi de village.
- Comptes Supabase Auth, modération avancée, notifications.
- Modèles de rendement (type DSSAT).

---

## 16. Règles du hackathon
- Le code écrit avant l'événement doit être **déclaré** : tenir dans `README.md` une section « Travail préparatoire » (date, contenu).
- Ne jamais présenter un scénario comme une prévision, ni un score comme un rendement.
