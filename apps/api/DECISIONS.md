# DECISIONS — Backend Field Shift Togo

Décisions prises pendant l'implémentation. Les décisions 1 à 12 ont été tranchées par le porteur du projet ; les suivantes (D-xx) par l'agent de code, en choisissant l'option la plus simple.

## Décisions tranchées par le porteur du projet

1. **R003 et format des règles** : l'ancienne condition `scenario == 'dry'` ne se déclenche jamais (ids réels `dry_minus20`, `dry_hot`). Remplacée par le format structuré §8.5 (`scenario.rainfall_change_pct < 0`) ; **R004** ajoutée. Les fichiers originaux du pack restent intacts dans `data/` ; la nouvelle version est dans `data/seed/rules.json`.
2. **Bornes des phases (§9.1)** : `f = (i + 0.5) / n`, bornes cumulées 0,20 / 0,50 / 0,80 / 1,00 : `f < 0.20` → `initial`, `f < 0.50` → `development`, `f < 0.80` → `mid`, sinon `late`. Interpolation du Kc : position dans la phase = `(f − début_phase) / longueur_phase`.
3. **Ordre de calcul de Ks (§9.3)** : Ks est calculé avec le stock d'eau **au début** de la décade, avant d'ajouter la pluie, comme dans le pseudo-code.
4. **`harvest_dekad`** = dernière décade du cycle, avec passage de 36 à 1.
5. **Exemple du §9.3** : « août D1 → août D3 » n'est qu'une illustration ; l'algorithme fait foi.
6. **`mean_stress`** (tri §9.5) = moyenne simple des `stress_index` des saisons de la séquence.
7. **Source « la plus faible » (§4)** : calculée sur climat, cultures, sols et règles avec l'ordre `synthetic_demo < provisional_demo < computed/nasa_power`. Le scénario n'entre pas dans ce calcul, mais figure **toujours** dans `data_provenance` (`synthetic_scenario`) et `explanations_fr` contient « Scénario hypothétique… ».
8. **Altitude en mode hors ligne** : `elevation_m` est optionnel (`null`) dans `ZonePack`. Le climat de secours fournit directement `et0_mm` ; aucune altitude inventée.
9. **V005 / V006** : version backend de la spec (§9.7) — paquet `--offline` ⇒ `synthetic_demo` ; paquet NASA ⇒ `nasa_power` + `warnings_fr` non vide. Les versions « interface » du pack concernent le frontend.
10. **Arrondi à 2 décimales** uniquement à la sérialisation (sérialiseur Pydantic `R2`), jamais pendant le calcul.
11. **Riz** traité en culture pluviale dans le bilan hydrique (mentionné dans `assumptions_fr`).
12. **Noms de zones** : `name_fr` court (« Maritime », « Plateaux », « Kara ») ; le nom long du pack est conservé dans `name_long_fr` (seed).

## Décisions de l'agent

- **D-01 — Emplacement du pack** : le zip est décompressé à la racine du dépôt : `data/` (fichiers source inchangés), `schemas/exemples_validation.json`, `docs/`, `scripts/fetch_historical_weather.py`. Le `README.md` du pack, qui entrerait en conflit avec le README du dépôt, est copié tel quel sous `docs/README_pack.md`.
- **D-02 — Base par défaut** : sans `.env`, `DATABASE_URL` vaut un fichier SQLite local (`apps/api/fieldshift.db`) pour que l'API tourne sous Windows sans Docker. La liste des variables (avec l'URL Postgres de la spec et la variante SQLite) est dans la section « Configuration » du README (`.env.example` a été supprimé le 2026-11-08).
- **D-03 — Chemins relatifs** : `PACKS_DIR` et `DATA_DIR` relatifs sont résolus par rapport à `apps/api/` (et non au répertoire courant), pour que les commandes marchent quel que soit l'endroit d'où on les lance.
- **D-04 — Colonne `source_type` sur `devices` et `plots`** : ajout (nullable) au modèle §11 pour marquer les appareils/parcelles de démo `synthetic_demo` comme l'exige `cli seed`. `NULL` pour les vrais utilisateurs.
- **D-05 — Données de démo** : identifiants déterministes (UUID v5 dérivés de `plot_id`), horodatage fixe (2026-11-01T00:00Z) → `seed` est strictement idempotent. Chaque parcelle de démo reçoit une `plot_season` `2025-main` avec sa `previous_crop_id` (valeur du pack). Les appareils de démo ont un `token_hash` sentinelle (`demo-device-no-token`) qui ne peut correspondre à aucun sha256 : ils ne peuvent pas s'authentifier.
- **D-06 — `seed` ne crée pas les tables** : il faut `alembic upgrade head` avant. Pour un démarrage rapide sans Alembic, `python -m app.cli init-db` crée les tables directement. Les tests utilisent `create_all` sur SQLite.
- **D-07 — Altitude dans la base** : le seed ne remplit pas `zones.elevation_m` et ne l'écrase jamais ; elle sera fournie par NASA POWER (pipeline).
- **D-08 — Erreurs** : toutes les erreurs (y compris 404 de routage et 422 de validation) suivent `{"error": {"code", "message_fr"}}` ; les 422 ajoutent `details` (champ supplémentaire, non contradictoire avec §10.8).
- **D-09 — Labels de saisons Plateaux** : la spec ne donne pas de libellé ; repris de Maritime (« Grande saison » / « Petite saison »).
- **D-10 — Libellés des scénarios** : `label_fr` courts (« Pluie −20 % », « Température +2 °C », « Pluie −20 % et +2 °C », « Référence (climat moyen) »).
- **D-11 — Import du pipeline** : `pipeline/` est à la racine du dépôt et n'est pas packagé ; `app.cli` ajoute la racine du dépôt au `sys.path`, et le pipeline se lance depuis la racine (`python -m pipeline.run_all`).
- **D-12 — `ea` FAO-56** : calculée à partir de RH2M moyenne (`ea = RH/100 × es`), simplification imposée par la spec (NASA POWER ne fournit pas RHmax/RHmin dans la requête retenue).

## P2 — Moteur de référence

- **D-13 — Périodes critiques** : suites de décades consécutives du cycle avec `stress > 0.2`, **coupées au changement de phase** (une période = une seule phase, ce qui donne une explication claire « manque d'eau en floraison/remplissage »). `mean_stress` = moyenne simple du stress de la période.
- **D-14 — WRSI** : `wrsi = 100 × ΣETa / ΣETc`, **borné à [0, 100]** (le bruit flottant donnait 100.00000000000001) ; `wrsi = 100` si `ΣETc = 0`.
- **D-15 — Nombres dans les textes français** : arrondi « demi vers le haut » `floor(x·10ⁿ + 0,5) / 10ⁿ` (reproductible à l'identique en TypeScript), virgule décimale, zéros finaux supprimés (`0,3`, `20`), signe explicite pour les scénarios (`+0`, `-20`). Stress : 2 décimales ; WRSI : entier ; scénario : 1 décimale.
- **D-16 — Ordre des explications** (`explanations_fr` de `simulate`) : 1) ligne « Scénario hypothétique… », 2) une ligne par période critique (ou « Pas de manque d'eau marqué… »), 3) « Besoins en eau couverts à … % ». `recommend` renvoie la ligne de scénario en tête ; chaque saison porte les explications de sa simulation.
- **D-17 — `sowing_dekad` par défaut** (`/simulate` sans décade) : la décade de semis de la première saison de la zone (`seasons[0]`, saison principale).
- **D-18 — `evaluate_sequence`** : fonction du moteur qui note **une séquence donnée** avec exactement la logique de `recommend` (utilisée pour V001–V003 et les cas golden correspondants). Pas de nouvel endpoint.
- **D-19 — Déterminisme de la rotation** (à reproduire côté TS) : séquences énumérées dans l'ordre produit cartésien des cultures **dans l'ordre du paquet** ; `rule_pts` sommés dans l'ordre des règles du paquet ; `total_score` sommé dans l'ordre des saisons ; départage final par comparaison élément par élément des `crop_id` (ordre des chaînes). Le cache de simulations est local à chaque appel.
- **D-20 — Provenance des résultats** : `simulate` liste `climate`, `crops`, `soils`, `scenario` ; `recommend` ajoute `rules` et `scoring`. `scoring` (provisional_demo) n'entre pas dans le calcul de la source la plus faible (décision #7), sans effet pratique.
- **D-21 — Évaluateur de règles** : attribut absent ou comparaison impossible (ex. `None < 0`) ⇒ condition fausse. Validation du format des conditions au chargement (Pydantic : champ `prev|next|scenario.<attr>`, opérateur dans la liste fermée).
- **D-22 — Champs de sortie** : `SimulationResult` et `critical_periods` ont **exactement** les champs du §9.3 (pas d'ajout, pour ne pas toucher au contrat). Le format détaillé de `recommend` (non figé par la spec) est défini par `app/schemas/engine.py::RotationResult`.

## P3 — Pipeline (décisions prises en préparant P2)

- **D-23 — Secours synthétique** : `synthetic_fallback` génère une **série fictive** (année × décade, 1991-2020, graine fixe) puis passe par le **même calcul de normales** que le chemin NASA (moyennes, p20, CV, démarrage de saison). Pas de `trend` (`null`) : une série fictive ne peut pas fonder un « constat historique ». Pas d'altitude (`null`).
- **D-24 — Fichier de paquet = JSON canonique** (clés triées, séparateurs compacts, UTF-8) : le fichier lui-même est la forme canonique, donc `sha256(fichier)` = sha256 canonique = ETag.
- **D-25 — `data_provenance` du paquet** : les 4 entrées du §7 + `soils`, `scoring` et `sowing_calendar` (`computed` si toutes les saisons ont un démarrage calculé, sinon `provisional_demo`). Ajout d'éléments de liste, pas de changement de schéma.
- **D-26 — V005/V006** : testés dans `tests/test_pipeline.py` sur les paquets construits (ils dépendent de P3).
- **D-27 — Pas de repli silencieux** : sans `--offline`, une panne de NASA POWER arrête le pipeline avec une erreur ; le secours synthétique ne s'utilise que sur demande explicite (`--offline`), pour ne jamais faire passer du fictif pour du NASA.
- **D-28 — Cache brut** : chaque tranche de 10 ans est gardée telle quelle (`data/raw/power/{zone}/chunk_*.json`) ; un nouvel appel ne retélécharge pas (sauf `--force`). Le CSV et le `.meta.json` du §6.1 sont reconstruits depuis ce cache.
- **D-29 — Décades partielles** : avec ≤ 3 jours manquants, `p_mm`/`et0_mm` = somme des jours disponibles (pas d'extrapolation). Sur 1991-2025, NASA POWER n'a renvoyé **aucun** jour manquant pour les 3 zones.
- **D-30 — Statistiques** : `p_p20` = percentile 20 avec interpolation linéaire (numpy) ; `p_cv` = écart-type (ddof = 1) / moyenne. Tendance calculée sur les seules années complètes (36 décades valides) ; `null` si la période récente n'est pas entièrement couverte ou s'il y a moins de 20 années de référence.
- **D-31 — Fichier intermédiaire** : `data/processed/climatology_{zone}.json` (normales, tendance, démarrages, altitude, avertissements) est l'entrée de `build_packs`. Le dernier mode lancé (NASA ou `--offline`) l'écrase ; `run_all --packs-dir` permet d'écrire les paquets ailleurs.
- **D-32 — Base de données** : le pipeline ne touche pas la base (fichiers uniquement). `python -m app.cli seed` charge `climate_dekad` (depuis `data/processed/dekad_*.csv`, suppression + insertion par zone), l'altitude NASA des zones et la table `packs` (depuis `packs/manifest.json`).
- **D-33 — Démarrages calculés (données NASA 1991-2020)** : Maritime grande saison = décade 8 (= début de la fenêtre de recherche, les pluies de mars suffisent déjà), petite saison = 24 ; Plateaux 8 / 24 ; Kara 13 (mai D1). Toutes les dates de semis des paquets NASA sont donc `computed`.
- **D-34 — Tendance observée** (constat historique, pas une prévision) : Maritime pluie +24,7 %, +0,33 °C ; Plateaux +5,2 %, +0,44 °C ; Kara −1,2 %, +0,33 °C (2016-2025 vs 1991-2020). Valeurs NASA POWER publiées telles quelles.

## P4 — API zones / paquets / moteur

- **D-35 — Référentiels** : `/crops`, `/scenarios`, `/soils` servent `data/seed/*.json` chargé au démarrage (le même contenu que dans les paquets). `/zones` renvoie chaque zone **au format `zone` du paquet** (dates de semis calculées) ; sans paquet, repli sur le seed avec les dates provisoires (`sowing_source = provisional_demo`).
- **D-36 — Codes HTTP du moteur** : `unknown_zone` (pas de paquet) → 404 ; autres erreurs du moteur (`unknown_crop`, `unknown_soil`, `unknown_scenario`, `invalid_horizon`, `invalid_sowing_dekad`, `zone_mismatch`) → 400 ; corps mal formé (ex. `priority` inconnue) → 422 `validation_error`.
- **D-37 — `/rotation/compare-scenarios`** : réponse `{zone_id, soil_id, previous_crop_id, priority, results: [RotationResult par scénario, dans l'ordre demandé], disclaimer_fr}`. `scenario_ids` non vide et sans doublon.
- **D-38 — Manifest** : `url` relative (`/api/v1/packs/{zone_id}`) pour fonctionner derrière n'importe quel hôte. Paquets lus et validés (`ZonePack`) une fois au démarrage ; un fichier invalide est journalisé et ignoré.
- **D-39 — Golden** : `packs/golden_cases.json` embarque les 3 paquets utilisés (+ sha256) pour être autosuffisant ; 39 cas : 30 `simulate` (Kara, 5 cultures × `sandy_loam`/`clay` × `baseline`/`dry_minus20`/`hot_plus2`, semis par défaut), 6 `recommend` (3 parcelles de démo, chacune sur le paquet de **sa** zone, × `baseline`/`dry_minus20`, horizon par défaut), 3 `evaluate_sequence` (V001–V003, Kara, `sandy_loam`, priorité `balanced`). **À régénérer après chaque reconstruction des paquets** (un test détecte un golden périmé).
- **D-40 — Tests d'API** : ils utilisent des paquets `--offline` générés dans un dossier temporaire (indépendants du réseau et de `packs/`).

## P5 — Appareils, synchronisation, posts, synthèse

- **D-41 — Enregistrement** : `POST /devices/register` renvoie 201 ; un `device_id` déjà enregistré → **409 `device_exists`** (pas de réémission de jeton : sinon quiconque connaît l'UUID pourrait voler l'identité). Une réinstallation génère un nouvel UUID côté client. `zone_id` inconnue → 400.
- **D-42 — Limitation de débit** : fenêtre glissante de 60 s en mémoire, `RATE_LIMIT_PER_MIN` requêtes par appareil sur les routes authentifiées, et par adresse IP sur `/devices/register`. Réinitialisée au redémarrage (une seule instance suffit pour le MVP).
- **D-43 — Push ligne par ligne** : une ligne invalide est rejetée **sans bloquer le lot** (`rejected: [{id, entity, reason, message_fr, server_row?}]`). Raisons : `invalid`, `unknown_zone`, `unknown_soil`, `unknown_crop`, `unknown_plot`, `forbidden`, `stale`. Traitement dans l'ordre `plots` → `plot_seasons` → `posts` (une saison peut référencer une parcelle du même push). `server_row` n'est renvoyé que pour `stale` (jamais la ligne d'un autre appareil).
- **D-44 — LWW et idempotence** : acceptation si la ligne n'existe pas ou si `incoming.updated_at > existing.updated_at`. Même `updated_at` **et** même contenu → rejeu : `accepted`, aucune écriture (`server_updated_at` inchangé). Même `updated_at` avec un contenu différent → `stale`. Tous les horodatages sont normalisés en UTC (naïf = UTC).
- **D-45 — Curseur serveur** : chaque ligne écrite par un push reçoit un `server_updated_at` strictement croissant (horloge serveur + 1 µs par ligne), ce qui rend la pagination stable. `server_time` est capturé **avant** les requêtes du pull. Pagination : au-delà de 500 lignes, `next_since` (= `server_time`) pointe sur la dernière ligne renvoyée ; le client rappelle avec ce curseur jusqu'à `next_since = null`. Limite connue : une écriture concurrente pile pendant un pull peut n'apparaître qu'au pull suivant (instance unique, risque négligeable).
- **D-46 — Pull** : lignes de l'appareil (`plots`, `plot_seasons`, `posts`) + posts publics de **sa** zone, suppressions logiques comprises (pierres tombales). Les posts n'exposent jamais le `device_id` de l'auteur : champs ajoutés `is_mine` et `author_name` (nom d'affichage choisi, éventuellement `null`).
- **D-47 — Posts** : `GET /posts` trié par `server_updated_at` décroissant, `before` = curseur exclusif, réponse `{posts, next_before}` ; `limit` 1–100 (défaut 20). `POST /posts` accepte un `id` client optionnel (UUID généré sinon ; 409 si déjà pris). `DELETE` = suppression logique par l'auteur (403 sinon, 404 si absent).
- **D-48 — Synthèse de zone** : `{zone_id, name_fr, region, climate, producers, recent_posts}`. `climate` = chiffres clés du paquet (cumul annuel P et ET0, température moyenne, décade la plus pluvieuse, `trend`, avertissements, saisons). `producers` : nombre de parcelles **réelles** (les parcelles de démo `synthetic_demo` ne sont jamais comptées), cultures par `season_label` avec seuil d'anonymat ≥ 3 parcelles distinctes, le reste regroupé en `{"crop_id": "other", "name_fr": "autres"}`.
- **D-49 — Pas de `GET /devices/me`** : non prévu au §10, donc non ajouté (le profil est renvoyé par `PATCH /devices/me`).

## P6 — Finition

- **D-50 — Docker non testé** : Docker n'est pas installé sur le poste ; `apps/api/Dockerfile` (contexte de build = racine du dépôt, utilisateur non root, `alembic upgrade head` + `seed` au démarrage) et `docker-compose.yml` (Postgres 16 + API) sont écrits mais **non exécutés**. Postgres : testé sur Supabase le 2026-11-08 (D-64).
- **D-51 — Fichiers générés versionnés** : `packs/` (paquets, manifest, schéma, golden) et `data/processed/` sont gardés dans le dépôt (~0,7 Mo) pour que l'API et le frontend fonctionnent sans relancer le pipeline ; `data/raw/` (cache NASA brut, ~7 Mo) est ignoré.
- **D-52 — Limite connue du moteur** : la simulation utilise le **climat moyen** décadaire (moyennes 1991-2020), ce qui lisse les épisodes secs : avec les données NASA réelles, les cultures semées au démarrage de saison montrent souvent peu de stress, même en `dry_minus20`. Les `p_p20` (« année sèche ») sont dans le paquet mais pas encore utilisés par le moteur (une évolution possible serait un scénario « année sèche » fondé sur `p_p20`, ce qui changerait le contrat du moteur : à décider avec le frontend).

## Revue de code (2026-11-08)

- **D-53 — Horodatage serveur au moment du commit** : les lignes écrites par `/sync/push` recevaient un `server_updated_at` calculé au **début** du push. Sur Postgres distant, un push de plusieurs centaines de lignes dure plusieurs secondes : un `pull` lancé pendant ce temps renvoyait un `server_time` plus récent que ces lignes encore non validées, qui étaient ensuite **sautées définitivement** (pire que la limite annoncée en D-45). Les lignes sont maintenant horodatées juste avant le `COMMIT`, par une horloge serveur **strictement croissante** (`app/services/clock.py::server_now`) qui sert aussi au `server_time` des pulls et aux posts. Sous Windows, l'horloge système avance par paliers d'environ 15 ms : sans cela, une ligne poussée puis tirée dans le même palier était renvoyée au pull suivant (test instable). Il reste une fenêtre d'un aller-retour réseau entre l'horodatage et le `COMMIT` (fermée par le recouvrement du curseur, D-62).
- **D-54 — Caractère NUL refusé** : PostgreSQL ne peut pas stocker U+0000 dans `text`/`varchar` (erreur asyncpg → 500). Toute chaîne reçue d'un client qui le contient est refusée (`422` ou ligne `invalid` dans un push).
- **D-55 — Dates hors limites** : une date comme `0001-01-01T00:00+05:00` débordait lors de la conversion en UTC (500). Elle donne maintenant une erreur de validation (`422`, ou ligne `invalid`). `since` et `before` sont validés de la même façon.
- **D-56 — Format d'erreur pour les 500 et les conflits** : une exception imprévue renvoie `{"error": {"code": "internal_error", ...}}` (détail seulement dans les journaux) ; une `IntegrityError` (deux insertions simultanées du même UUID) renvoie `409 conflict`.
- **D-57 — `FRONTEND_ORIGIN`** : accepte plusieurs origines séparées par des virgules (production + prévisualisation) ; la barre oblique finale est retirée (le navigateur envoie l'origine sans elle, sinon tout était bloqué par CORS).
- **D-58 — Moteur de base de données** : sous SQLite, `PRAGMA foreign_keys=ON` à chaque connexion, pour que les tests refusent les mêmes lignes que Postgres ; sous Postgres, `pool_pre_ping` + `pool_recycle=1800` (le pooler Supabase ferme les connexions inactives).
- **D-59 — Limiteur de débit** : les clés inactives depuis plus d'une fenêtre sont oubliées quand la table dépasse 10 000 clés (avant : une entrée par IP/appareil pour toujours).

### Changements de contrat validés par le porteur du projet (2026-11-08)

- **D-60 — Posts supprimés sans texte** : dans `/sync/pull`, un post supprimé (pierre tombale) d'un **autre** appareil est renvoyé avec `body: ""`. Avant, un nouvel appareil de la zone récupérait le texte des messages effacés. L'auteur garde son propre texte.
- **D-61 — Taille d'un push** : 500 lignes maximum par entité (`plots`, `plot_seasons`, `posts`) et par `/sync/push` ; au-delà, `422 validation_error`. Le client envoie les gros lots en plusieurs fois.
- **D-62 — Recouvrement du curseur de pull** : le `server_time` d'une dernière page vaut `max(since, horloge serveur − 5 s)`. Une ligne horodatée juste avant un pull mais validée juste après n'est plus perdue : elle revient au pull suivant. Conséquence pour le client : un pull peut renvoyer des lignes déjà reçues (moins de 5 s), qu'il met à jour par `id`. Les pages intermédiaires (`next_since`) ne changent pas.
- **D-63 — Curseur des posts** : `next_before` vaut `"<server_updated_at ISO>|<id du post>"` et se renvoie tel quel dans `before` ; tri `server_updated_at` puis `id` décroissants. Deux posts au même instant ne sont plus sautés. L'ancien format (date ISO seule) reste accepté ; un curseur illisible donne `422`.

## Premier passage sur PostgreSQL (Supabase, 2026-11-08)

- **D-64 — Résultat** : Postgres 17.11 (Supabase, Session pooler port 5432, `ssl=require`). `alembic upgrade head`, `seed` (deux fois : idempotent), comptes conformes à `docs/SUPABASE_SETUP.md`, RLS activé sans `FORCE` sur les 12 tables (le rôle `anon` ne voit aucune ligne et ne peut rien insérer), API en ligne : `/health` (`db: ok`, `packs_count: 3`), `/rotation/recommend` sur la parcelle de démo de Kara, cycle `devices/register` → `sync/push` (+ rejeu, `stale`, NUL refusé) → `sync/pull`, posts, synthèse de zone. **Aucune erreur propre à Postgres** : les corrections préventives de la revue (D-54, D-55, D-58) ont suffi. Les lignes de test ont été supprimées ensuite.
- **D-65 — Port du pooler** : l'URL fournie visait le Transaction pooler (6543), incompatible avec le cache de requêtes préparées d'asyncpg ; on utilise le Session pooler (même hôte, port 5432), comme le prévoit le guide.
- **D-66 — `.env.example` supprimé** : la liste des variables avec valeurs d'exemple sans secret est dans le README (section « Configuration ») ; `apps/api/.env` reste ignoré par git.
