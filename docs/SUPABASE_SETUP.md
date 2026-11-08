# Mise en place de Supabase pour le backend Field Shift

Ce guide explique comment préparer une base Supabase (PostgreSQL) pour l'API FastAPI de `apps/api`.
Tout ce qui suit vient du code du dépôt : modèles `apps/api/app/models/__init__.py`, migration
`apps/api/alembic/versions/0001_initial_schema.py`, seed `apps/api/app/services/seed_service.py`,
config `apps/api/app/config.py`.

> ⚠️ **À savoir avant de commencer** : jusqu'ici, la migration et le seed n'ont tourné **que sur SQLite**
> (voir `apps/api/DECISIONS.md`, D-50). Les types utilisés sont portables (`JSON`, `Uuid`), donc Postgres
> devrait passer sans souci, mais le premier passage sur Supabase sera aussi le premier test réel sur Postgres.
> Faites-le sur un projet Supabase vide, en suivant l'ordre ci-dessous.

---

## 1. Les tables (§11)

Il y a **11 tables métier**, plus une 12ᵉ technique créée automatiquement par Alembic :
`alembic_version` (une seule ligne, le numéro de migration appliqué, `0001`).

Correspondance des types (SQLAlchemy → PostgreSQL) :

| SQLAlchemy | PostgreSQL |
|---|---|
| `String(n)` | `varchar(n)` |
| `Text` | `text` |
| `Integer` | `integer` |
| `Float` | `double precision` |
| `Boolean` | `boolean` |
| `JSON` | `json` (pas `jsonb`, choix voulu pour rester compatible SQLite) |
| `Uuid` | `uuid` |
| `Date` | `date` |
| `DateTime(timezone=True)` | `timestamptz` |

Dans les tableaux : **PK** = clé primaire, **FK** = clé étrangère, « null ? » = la colonne accepte NULL.

### 1.A Tables de référence (remplies par le seed)

Ce sont les données de référence. L'application les lit, les utilisateurs ne les modifient jamais.

#### `zones`
Les zones agro-climatiques du Togo couvertes par l'app (coordonnées, saisons de culture).

| Colonne | Type | null ? | Clé |
|---|---|---|---|
| zone_id | varchar(64) | non | **PK** |
| name_fr | varchar(128) | non | |
| region | varchar(128) | non | |
| latitude | double precision | non | |
| longitude | double precision | non | |
| elevation_m | double precision | oui | |
| seasons | json | non | |
| source_type | varchar(64) | non | |

Index : aucun en plus de la PK.

#### `crops`
Les cultures avec leurs paramètres agronomiques (coefficients Kc, profondeur racinaire, cycle…).

| Colonne | Type | null ? | Clé |
|---|---|---|---|
| crop_id | varchar(64) | non | **PK** |
| name_fr | varchar(128) | non | |
| family | varchar(64) | non | |
| n_fixing | boolean | non | |
| cycle_days | integer | non | |
| water_need | varchar(32) | non | |
| drought_tolerance | varchar(32) | non | |
| food_staple | boolean | non | |
| kc_ini | double precision | non | |
| kc_mid | double precision | non | |
| kc_end | double precision | non | |
| root_depth_m | double precision | non | |
| depletion_p | double precision | non | |
| phases | json | non | |
| source_type | varchar(64) | non | |
| source_note | text | oui | |

Index : aucun en plus de la PK.

#### `soils`
Les types de sol et leur réserve utile en eau (TAW, en mm par mètre de sol).

| Colonne | Type | null ? | Clé |
|---|---|---|---|
| soil_id | varchar(64) | non | **PK** |
| label_fr | varchar(128) | non | |
| taw_mm_per_m | double precision | non | |
| source_type | varchar(64) | non | |

Index : aucun en plus de la PK.

#### `rotation_rules`
Les règles de rotation (bonus ou malus selon la culture précédente) utilisées par le moteur de recommandation.

| Colonne | Type | null ? | Clé |
|---|---|---|---|
| rule_id | varchar(32) | non | **PK** |
| effect | varchar(16) | non | |
| delta | double precision | non | |
| conditions | json | non | |
| explanation_fr | text | non | |
| source_type | varchar(64) | non | |

Index : aucun en plus de la PK.

#### `scenarios`
Les scénarios climatiques (variation de pluie en %, de température en °C) qu'on applique aux simulations.

| Colonne | Type | null ? | Clé |
|---|---|---|---|
| scenario_id | varchar(64) | non | **PK** |
| label_fr | varchar(128) | non | |
| rainfall_change_pct | double precision | non | |
| temperature_change_c | double precision | non | |
| source_type | varchar(64) | non | |
| note_fr | text | non | |

Index : aucun en plus de la PK.

#### `climate_dekad`
L'historique climatique par décade (périodes de 10 jours) et par zone, de 1991 à 2025, issu de NASA POWER.

| Colonne | Type | null ? | Clé |
|---|---|---|---|
| zone_id | varchar(64) | non | **PK** (1/3), **FK → zones.zone_id** |
| year | integer | non | **PK** (2/3) |
| dekad | integer | non | **PK** (3/3) |
| p_mm | double precision | oui | |
| et0_mm | double precision | oui | |
| tmean_c | double precision | oui | |
| tmax_c | double precision | oui | |
| n_days | integer | non | |
| n_missing | integer | non | |
| source_type | varchar(64) | non | |

Clé primaire composée : `(zone_id, year, dekad)`. Index : aucun en plus de la PK.

#### `packs`
Le registre des paquets de zone publiés (version, empreinte sha256, taille), lu depuis `packs/manifest.json`.

| Colonne | Type | null ? | Clé |
|---|---|---|---|
| zone_id | varchar(64) | non | **PK** (1/2), **FK → zones.zone_id** |
| pack_version | varchar(32) | non | **PK** (2/2) |
| sha256 | varchar(64) | non | |
| size_bytes | integer | non | |
| generated_at | timestamptz | non | |

Clé primaire composée : `(zone_id, pack_version)`. Index : aucun en plus de la PK.

### 1.B Tables remplies par les utilisateurs

Ces tables se remplissent par l'API (inscription d'un appareil, synchronisation, publications).
**Le seed y ajoute quand même 3 lignes de démonstration** (voir §2.3), marquées `synthetic_demo`.

#### `devices`
Un téléphone ou navigateur enregistré (pas de compte utilisateur, on s'authentifie par jeton d'appareil).

| Colonne | Type | null ? | Clé |
|---|---|---|---|
| device_id | uuid | non | **PK** |
| token_hash | varchar(64) | non | index `ix_devices_token_hash` |
| display_name | varchar(128) | oui | |
| zone_id | varchar(64) | oui | **FK → zones.zone_id** |
| priority | varchar(32) | oui | |
| created_at | timestamptz | non | |
| last_seen_at | timestamptz | oui | |
| source_type | varchar(64) | oui | (ajout à §11, D-04 : `synthetic_demo` ou NULL) |

Index : `ix_devices_token_hash (token_hash)`.

#### `plots`
Les parcelles d'un appareil (nom, zone, surface, sol). Elles sont synchronisées entre le hors-ligne et le serveur.

| Colonne | Type | null ? | Clé |
|---|---|---|---|
| id | uuid | non | **PK** |
| device_id | uuid | non | **FK → devices.device_id** |
| zone_id | varchar(64) | non | **FK → zones.zone_id** |
| name | varchar(128) | non | |
| area_ha | double precision | oui | |
| soil_id | varchar(64) | oui | **FK → soils.soil_id** |
| updated_at | timestamptz | non | |
| server_updated_at | timestamptz | non | |
| deleted | boolean | non | |
| source_type | varchar(64) | oui | (ajout à §11, D-04) |

Index : `ix_plots_device_id (device_id)`, `ix_plots_server_updated_at (server_updated_at)`.

#### `plot_seasons`
L'historique d'une parcelle saison par saison (culture semée, date de semis, notes de rendement et de pertes).

| Colonne | Type | null ? | Clé |
|---|---|---|---|
| id | uuid | non | **PK** |
| plot_id | uuid | non | **FK → plots.id** |
| device_id | uuid | non | **FK → devices.device_id** |
| season_label | varchar(32) | non | |
| crop_id | varchar(64) | oui | **FK → crops.crop_id** |
| sowing_date | date | oui | |
| yield_note | text | oui | |
| losses_note | text | oui | |
| updated_at | timestamptz | non | |
| server_updated_at | timestamptz | non | |
| deleted | boolean | non | |

Index : `ix_plot_seasons_plot_id (plot_id)`, `ix_plot_seasons_device_id (device_id)`,
`ix_plot_seasons_server_updated_at (server_updated_at)`.

#### `posts`
Les messages publiés par les appareils sur le fil d'une zone.

| Colonne | Type | null ? | Clé |
|---|---|---|---|
| id | uuid | non | **PK** |
| device_id | uuid | non | **FK → devices.device_id** |
| zone_id | varchar(64) | non | **FK → zones.zone_id** |
| body | text | non | |
| updated_at | timestamptz | non | |
| server_updated_at | timestamptz | non | |
| deleted | boolean | non | |

Index : `ix_posts_device_id (device_id)`, `ix_posts_server_updated_at (server_updated_at)`,
`ix_posts_zone_server_updated_at (zone_id, server_updated_at)`.

> Note : aucune FK n'a de `ON DELETE CASCADE`. Les suppressions passent par le drapeau `deleted`
> (suppression logique), jamais par un `DELETE`.

---

## 2. Comment les tables sont créées

### 2.1 Pas de création à la main

**Ne créez aucune table à la main dans Supabase** (ni Table Editor, ni SQL Editor).
`alembic upgrade head` crée les 11 tables, leurs clés et leurs index, plus la table `alembic_version`.
Si vous créez des tables à la main, Alembic tombera en erreur (« relation already exists ») ou le
schéma ne correspondra plus au code.

Le seed (`python -m app.cli seed`) **ne crée pas les tables** (D-06) : il faut lancer la migration avant.

N'utilisez pas non plus `python -m app.cli init-db` sur Supabase : cette commande crée les tables sans
Alembic, donc sans `alembic_version`, et elle est prévue uniquement pour SQLite en local.

### 2.2 Commandes PowerShell, dans l'ordre

À lancer depuis votre PC. On suppose que le venv existe déjà et que les dépendances sont installées
(`python -m pip install -e "apps/api[dev]"`, voir le README).

```powershell
# 0) Se placer dans le projet et activer le venv
cd C:\Users\User\agri_shift_backend
.\.venv\Scripts\Activate.ps1
cd apps\api

# 1) Donner l'URL Supabase pour CETTE session PowerShell uniquement
#    Guillemets SIMPLES obligatoires : avec des guillemets doubles, PowerShell
#    remplacerait un éventuel « $ » du mot de passe.
$env:DATABASE_URL = 'postgresql+asyncpg://postgres.<PROJECT_REF>:<MOT_DE_PASSE>@<HOTE_POOLER>:5432/postgres?ssl=require'

# 2) Tester la connexion (base vide : aucune révision affichée, mais aucune erreur)
python -m alembic current

# 3) Migration : crée les 11 tables + alembic_version
python -m alembic upgrade head

# 4) Vérifier la révision appliquée -> doit afficher : 0001 (head)
python -m alembic current

# 5) Seed : référentiels + climat + packs + 3 parcelles de démo (idempotent, relançable)
python -m app.cli seed
#    Sortie attendue :
#    Seed OK: zones=3, crops=5, soils=4, rules=4, scenarios=7, demo_plots=3, climate_dekad=3780

# 6) Vérification de bout en bout : démarrer l'API en local, branchée sur Supabase
python -m uvicorn app.main:app
#    Dans un AUTRE terminal PowerShell :
#    Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
#    -> status = ok, db = ok, packs_count = 3
#    Puis Ctrl+C pour arrêter l'API.

# 7) Effacer l'URL de la session (elle contient le mot de passe)
Remove-Item Env:DATABASE_URL
```

Remarques :
- `DATABASE_URL` est lu par `app/config.py` (pydantic-settings). Une variable d'environnement a la priorité
  sur le fichier `apps/api/.env`. Vous pouvez aussi mettre l'URL dans `apps/api/.env` (il est dans
  `.gitignore`). La liste des variables est dans la section « Configuration » du `README.md` (avec des valeurs d'exemple, jamais la vraie URL).
- Le seed lit des fichiers locaux : `data/seed/*.json`, `data/synthetic/parcelles_demo.json`,
  `data/processed/dekad_*.csv`, `packs/manifest.json` et `data/raw/power/*.meta.json` (pour l'altitude).
  Comme `data/raw/` est dans `.gitignore`, **lancez le seed depuis votre PC** et pas depuis un clone neuf :
  sinon `zones.elevation_m` restera vide.
- Le seed est idempotent : le relancer ne crée pas de doublons. `climate_dekad` est effacée puis
  rechargée zone par zone.
- `pytest` n'utilise jamais `DATABASE_URL` : les tests tournent sur une base SQLite temporaire.
  Vous pouvez donc les lancer sans risque pour Supabase.

### 2.3 Nombre de lignes attendu après le seed

À contrôler dans **Table Editor** (le compteur affiché sous chaque table) ou avec la requête plus bas.

**Tables de référence**

| Table | Lignes | D'où ça vient |
|---|---:|---|
| zones | **3** | `data/seed/zones.json` (kara_kara, maritime_lome, plateaux_kpalime) |
| crops | **5** | `data/seed/crops.json` |
| soils | **4** | `data/seed/soils.json` |
| rotation_rules | **4** | `data/seed/rules.json` |
| scenarios | **7** | `data/seed/scenarios.json` |
| climate_dekad | **3 780** | 3 zones × 35 ans (1991-2025) × 36 décades = 3 × 1 260 |
| packs | **3** | `packs/manifest.json` (une version par zone) |

**Tables utilisateurs (juste après le seed)**

| Table | Lignes | Détail |
|---|---:|---|
| devices | **3** | appareils de démo, `source_type = 'synthetic_demo'` |
| plots | **3** | parcelles de démo, `source_type = 'synthetic_demo'` |
| plot_seasons | **3** | culture précédente de chaque parcelle de démo (saison `2025-main`) |
| posts | **0** | |
| alembic_version | **1** | `version_num = '0001'` |

Les appareils de démo ne peuvent pas s'authentifier : leur `token_hash` vaut `demo-device-no-token`,
qui ne peut jamais être un sha256.

Requête de contrôle à coller dans **SQL Editor** :

```sql
select 'zones' as table_name, count(*) from public.zones
union all select 'crops', count(*) from public.crops
union all select 'soils', count(*) from public.soils
union all select 'rotation_rules', count(*) from public.rotation_rules
union all select 'scenarios', count(*) from public.scenarios
union all select 'climate_dekad', count(*) from public.climate_dekad
union all select 'packs', count(*) from public.packs
union all select 'devices', count(*) from public.devices
union all select 'plots', count(*) from public.plots
union all select 'plot_seasons', count(*) from public.plot_seasons
union all select 'posts', count(*) from public.posts
union all select 'alembic_version', count(*) from public.alembic_version;
```

Si `climate_dekad` ou `packs` valent 0, c'est que `data/processed/dekad_*.csv` ou `packs/manifest.json`
manquent sur votre PC. Lancez `python -m pipeline.run_all` depuis la racine (voir le README), puis relancez le seed.

---

## 3. La connexion

### 3.1 Format de `DATABASE_URL`

Le projet utilise SQLAlchemy en mode asynchrone avec le pilote **asyncpg**. Le préfixe doit donc être
`postgresql+asyncpg://`, et pas `postgresql://` ni `postgres://` comme dans l'URL copiée depuis Supabase.

```
postgresql+asyncpg://<UTILISATEUR>:<MOT_DE_PASSE>@<HOTE>:<PORT>/postgres?ssl=require
```

Exemple avec le Session pooler (remplacez les valeurs entre chevrons) :

```
postgresql+asyncpg://postgres.<PROJECT_REF>:<MOT_DE_PASSE>@aws-0-eu-west-3.pooler.supabase.com:5432/postgres?ssl=require
```

- **Utilisateur** : avec le pooler, c'est `postgres.<PROJECT_REF>` (avec le point). Avec la connexion directe, c'est `postgres`.
- **Base** : `postgres`, la base par défaut de Supabase.
- **Mot de passe** : celui choisi à la création du projet (Project Settings → Database → Reset database password si vous l'avez perdu).
  S'il contient des caractères spéciaux, il faut les **encoder** dans l'URL : `@`→`%40`, `#`→`%23`,
  `/`→`%2F`, `:`→`%3A`, `%`→`%25`, `?`→`%3F`. Le plus simple : choisir un mot de passe long fait
  uniquement de lettres et de chiffres.
- **Hôte** : copiez-le tel quel depuis le bouton **Connect** de Supabase. Le préfixe `aws-0-…` / `aws-1-…`
  et la région changent d'un projet à l'autre.

La même URL sert à l'API, à Alembic (`alembic/env.py` la lit dans la config) et au seed.

### 3.2 Quelle URL prendre dans « Connect » : **Session pooler (port 5432)**

| Option | Hôte / port | Verdict pour ce projet |
|---|---|---|
| Direct connection | `db.<ref>.supabase.co:5432` | ❌ Seulement en **IPv6** (sauf add-on IPv4 payant). Beaucoup de box internet et d'hébergeurs n'ont pas d'IPv6, et la connexion échoue alors. |
| **Session pooler** | `aws-…pooler.supabase.com:5432` | ✅ **À prendre.** IPv4 et IPv6. Chaque client garde sa propre connexion Postgres pendant toute la session, comme une connexion directe. Les requêtes préparées d'asyncpg marchent donc, sans rien changer au code. Convient à l'API, à Alembic et au seed. |
| Transaction pooler | `aws-…pooler.supabase.com:6543` | ❌ La connexion Postgres change à chaque transaction. Or asyncpg met en cache des requêtes préparées, et ça provoque des erreurs du type `prepared statement "__asyncpg_stmt_…" does not exist / already exists`. Pour s'en sortir il faudrait modifier `app/db.py` et `alembic/env.py`. Ce mode vise surtout le serverless avec des milliers de connexions courtes, ce qui n'est pas notre cas. |

### 3.3 Réglages asyncpg

- **`statement_cache_size`** : **rien à régler avec le Session pooler.** Ce réglage (`statement_cache_size=0`)
  ne sert qu'en Transaction pooler, et il faudrait alors le passer par `connect_args` dans
  `create_async_engine(...)`, dans `app/db.py` et dans `alembic/env.py`. Le mettre dans l'URL ne marche
  pas de façon fiable : asyncpg le recevrait sous forme de texte. C'est une raison de plus pour rester
  sur le port 5432.
- **SSL** : ajoutez **`?ssl=require`** à la fin de l'URL. SQLAlchemy le transmet tel quel à asyncpg,
  qui chiffre alors la connexion.
  ⚠️ Écrivez bien `ssl=require`. La forme `sslmode=require` est celle de psycopg/libpq, asyncpg la refuse.
  Vous pouvez aussi activer « Enforce SSL on incoming connections » dans Supabase
  (Project Settings → Database → SSL Configuration) pour refuser toute connexion non chiffrée.
- **Nombre de connexions** : par défaut, SQLAlchemy ouvre jusqu'à 15 connexions par processus
  (`pool_size=5` + `max_overflow=10`). Le Session pooler de Supabase a une limite par projet
  (« Pool Size », visible dans Project Settings → Database). Avec une seule instance de l'API, ça passe.
  Si vous montez à plusieurs instances ou workers et que l'erreur `max clients reached` apparaît,
  augmentez le Pool Size côté Supabase. Pensez aussi qu'Alembic et le seed prennent chacun une
  connexion le temps de leur exécution.

---

## 4. La sécurité

### 4.1 Activer RLS : oui, sur toutes les tables du schéma `public`

Supabase publie automatiquement les tables du schéma `public` par son **API REST (PostgREST)**, à l'adresse
`https://<ref>.supabase.co/rest/v1/...`. La clé `anon` (ou « publishable ») suffit pour s'en servir, et cette
clé est faite pour être publique. **Si RLS est désactivé, n'importe qui disposant de cette clé peut lire,
modifier ou supprimer les appareils, les parcelles et les posts**, sans jamais passer par FastAPI.
Le Security Advisor de Supabase le signale d'ailleurs en erreur (« RLS Disabled in Public »).

**À faire juste après `alembic upgrade head`** : activer RLS **sans créer aucune policy**.
Sans policy, les rôles `anon` et `authenticated` (ceux de l'API REST) n'ont accès à aucune ligne.

À coller dans **SQL Editor** (couvre les 11 tables + `alembic_version`) :

```sql
do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;
end $$;

-- Vérification : rowsecurity doit valoir true pour les 12 tables
select tablename, rowsecurity from pg_tables where schemaname = 'public' order by tablename;
```

**Est-ce que ça gêne le backend ? Non.** Le backend se connecte avec l'utilisateur `postgres`
(`postgres.<ref>` via le pooler), et c'est lui qui crée les tables lors de la migration. Il en est donc
**propriétaire**, et RLS ne s'applique pas au propriétaire d'une table. L'API, Alembic et le seed
continuent de fonctionner normalement.
⚠️ N'utilisez **pas** `FORCE ROW LEVEL SECURITY` : cette option appliquerait RLS au propriétaire aussi
et bloquerait le backend.

**Précaution supplémentaire (conseillée)** : le backend n'utilise pas du tout l'API REST de Supabase.
Vous pouvez donc la couper, dans Project Settings → Data API : désactivez la Data API, ou retirez
`public` des « Exposed schemas ». Gardez RLS activé quand même, au cas où.

**À chaque nouvelle migration qui ajoute une table**, relancez le bloc SQL ci-dessus (il ne fait rien
de plus sur les tables déjà protégées).

### 4.2 Les valeurs secrètes : jamais dans GitHub

| Valeur | Où la trouver | Secret ? |
|---|---|---|
| Mot de passe de la base | choisi à la création du projet | 🔒 **Oui** |
| `DATABASE_URL` complète (elle contient le mot de passe) | construite par vous | 🔒 **Oui** |
| Clé `service_role` / clé secrète `sb_secret_…` | Project Settings → API Keys | 🔒 **Oui** (contourne RLS). Le backend n'en a pas besoin, ne la copiez nulle part. |
| JWT secret du projet | Project Settings → JWT | 🔒 **Oui**. Inutile pour ce backend. |
| Clé `anon` / publishable `sb_publishable_…` | Project Settings → API Keys | Publique par conception. Le backend ne l'utilise pas. |
| URL du projet `https://<ref>.supabase.co`, project ref | Connect | Non secret, mais inutile de l'afficher partout. |

Points de vigilance dans ce dépôt :
- `apps/api/.env` et `apps/api/*.db` sont déjà dans `.gitignore`. Vérifiez qu'ils le restent.
- Ne mettez jamais l'URL Supabase dans `README.md` (section « Configuration » : exemples seulement), `docker-compose.yml`,
  `alembic.ini` ni dans un message de commit.
- Si le mot de passe se retrouve un jour dans un commit poussé, changez-le immédiatement dans Supabase
  (Reset database password). Le supprimer de l'historique ne suffit pas.

---

## 5. Récapitulatif : checklist dans l'ordre

**A. Projet Supabase**
- [ ] Créer le projet sur supabase.com. Choisir une région proche des utilisateurs (Europe de l'Ouest,
      par exemple Paris `eu-west-3`, pour le Togo) et un **mot de passe de base fort, uniquement lettres et chiffres**.
- [ ] Ranger ce mot de passe dans un gestionnaire de mots de passe.

**B. Récupérer l'URL**
- [ ] Ouvrir **Connect** → onglet de connexion → choisir **Session pooler** (port **5432**).
- [ ] Copier l'URI, puis : remplacer `postgresql://` par **`postgresql+asyncpg://`**, mettre le mot de passe
      à la place de `[YOUR-PASSWORD]` (encodé si besoin) et ajouter **`?ssl=require`** à la fin.
- [ ] Vérifier que l'utilisateur est bien `postgres.<PROJECT_REF>` et que la base est `postgres`.

**C. Migration** (PowerShell, depuis `apps\api`, venv activé)
- [ ] `$env:DATABASE_URL = '…'` (guillemets simples)
- [ ] `python -m alembic current` → aucune erreur
- [ ] `python -m alembic upgrade head`
- [ ] `python -m alembic current` → `0001 (head)`
- [ ] Dans Supabase **SQL Editor** : lancer le bloc **RLS** du §4.1, puis vérifier `rowsecurity = true` sur les 12 tables.

**D. Seed**
- [ ] `python -m app.cli seed` → `Seed OK: zones=3, crops=5, soils=4, rules=4, scenarios=7, demo_plots=3, climate_dekad=3780`

**E. Vérification**
- [ ] Table Editor ou requête du §2.3 : zones 3, crops 5, soils 4, rotation_rules 4, scenarios 7,
      climate_dekad 3780, packs 3, devices 3, plots 3, plot_seasons 3, posts 0, alembic_version 1.
- [ ] `python -m uvicorn app.main:app`, puis `Invoke-RestMethod http://127.0.0.1:8000/api/v1/health`
      → `status: ok`, `db: ok`, `packs_count: 3`.
- [ ] Security Advisor de Supabase : plus d'alerte « RLS disabled ».
- [ ] (Conseillé) Désactiver la Data API, ou retirer `public` des schémas exposés.
- [ ] `Remove-Item Env:DATABASE_URL`

**F. Variables d'environnement sur FastAPI Cloud**

À saisir dans les variables d'environnement / secrets de l'application, jamais dans le code :

| Variable | Valeur | Obligatoire ? |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres.<ref>:<mdp>@<hote-pooler>:5432/postgres?ssl=require` | 🔒 **Oui (secret)** |
| `FRONTEND_ORIGIN` | l'URL exacte du frontend en production, par exemple `https://mon-front.vercel.app`, sans `/` final | **Oui**. Par défaut c'est `http://localhost:3000`, ce qui bloquerait le frontend par CORS. |
| `RATE_LIMIT_PER_MIN` | `60` | Non (60 par défaut) |
| `LOG_LEVEL` | `info` | Non (`info` par défaut) |
| `PACKS_DIR` | chemin du dossier `packs/` | Seulement si `packs/` n'est pas à `../../packs` par rapport à `apps/api` dans le déploiement |
| `DATA_DIR` | chemin du dossier `data/` | Même remarque, avec `../../data` |

Remarques pour le déploiement :
- L'API lit `packs/` et `data/seed/` au démarrage (`app/main.py`). Ces dossiers doivent donc faire partie
  de ce qui est déployé, sinon `/health` affichera `packs_count: 0`.
- Le `Dockerfile` lance `alembic upgrade head` puis le seed à chaque démarrage. Si FastAPI Cloud ne
  passe pas par ce Dockerfile, rien ne se lance automatiquement : refaites les étapes **C** et **D**
  depuis votre PC après chaque nouvelle migration ou chaque nouveau build de paquets.
- Une fois déployé : `https://<votre-api>/api/v1/health` doit répondre `status: ok`, `db: ok`.
