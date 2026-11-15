# AUDIT_SOURCES_NASA — Field Shift Togo

> **Statut** : lecture seule — aucun code, aucun paquet, aucune donnée modifiés.
> **Date** : 2026-11-14 (hackathon J1).
> **Périmètre** : croisement des 24 ressources NASA du défi avec le dépôt `agri_shift_backend`.
> **Mots-clés recherchés** : SMAP, IMERG, GPM, Landsat, MODIS, VIIRS, NDVI, ECOSTRESS, SRTM, GAEZ, GLDAS, NLDAS, GEDI, ERA5, Sentinel, OpenET, EVLAND, GWETROOT, GWETTOP, ALLSKY, PRECTOTCORR, open-meteo, Kpalimé, Atakpamé.

---

## Étape 1 — Inventaire des ressources

### Légende

| Statut | Sens |
|---|---|
| **UTILISÉE** | Paramètre ou source actif dans le pipeline ou l'API (fichier + ligne indiqués) |
| **MENTIONNÉE** | Citée dans la spec ou le registre, mais jamais appelée |
| **NON UTILISÉE** | Absente du dépôt |

### Tableau d'inventaire

| # | Ressource / Paramètre | Statut | Fichier(s) | Ligne(s) | Note |
|---|---|---|---|---|---|
| 1 | **NASA POWER — PRECTOTCORR** (pluie corrigée) | **UTILISÉE** | `pipeline/config.py`, `pipeline/fetch_power.py` | config L26, fetch L28,37 | Paramètre principal du pipeline. Colonne `precip_mm` dans le CSV brut. Unité reçue : `mm/day` (confirmé `*.meta.json` L18). |
| 2 | **NASA POWER — ALLSKY_SFC_SW_DWN** (rayonnement global) | **UTILISÉE** | `pipeline/config.py`, `pipeline/fetch_power.py` | config L26, fetch L31,40,125-126 | Converti en MJ/m²/j si renvoyé en kWh/m²/j (×3,6). Colonne `rs_mj`. Unité effective stockée : `MJ/m^2/day` (confirmé `*.meta.json` L21). |
| 3 | **NASA POWER — T2M, T2M_MAX, T2M_MIN** (température 2 m) | **UTILISÉE** | `pipeline/config.py`, `pipeline/fetch_power.py`, `pipeline/et0.py` | config L26, fetch L25-27, et0 L52 | Utilisées dans ET0 FAO-56. Unité : `C`. |
| 4 | **NASA POWER — RH2M** (humidité relative 2 m) | **UTILISÉE** | `pipeline/config.py`, `pipeline/fetch_power.py`, `pipeline/et0.py` | config L26, fetch L29, et0 L53 | Utilisée pour `ea` (simplification D-12). Unité : `%`. |
| 5 | **NASA POWER — WS2M** (vent à 2 m) | **UTILISÉE** | `pipeline/config.py`, `pipeline/fetch_power.py`, `pipeline/et0.py` | config L26, fetch L30, et0 L68 | `u2` dans Penman-Monteith. Unité : `m/s`. |
| 6 | **NASA POWER — GWETROOT** (humidité sol couche racinaire) | **NON UTILISÉE** | — | — | Absent de `POWER_PARAMETERS`. Non demandé à l'API. |
| 7 | **NASA POWER — GWETTOP** (humidité sol couche de surface) | **NON UTILISÉE** | — | — | Absent de `POWER_PARAMETERS`. Non demandé à l'API. |
| 8 | **NASA POWER — EVLAND** (évapotranspiration terrestre modèle) | **NON UTILISÉE** | — | — | Absent de `POWER_PARAMETERS`. Non demandé à l'API. |
| 9 | **GPM IMERG** (précipitations satellite) | **MENTIONNÉE** | `pipeline/config.py`, `BACKEND_FIELD_SHIFT.md` | config L53, spec L607 | Enregistrée `implemented: False` dans `SOURCES`. Hors périmètre §15. |
| 10 | **SMAP** (humidité du sol micro-onde) | **MENTIONNÉE** | `pipeline/config.py`, `BACKEND_FIELD_SHIFT.md` | config L54, spec L607 | Enregistrée `implemented: False`. Hors périmètre §15. |
| 11 | **MODIS / VIIRS — NDVI** (végétation) | **MENTIONNÉE** | `pipeline/config.py`, `BACKEND_FIELD_SHIFT.md` | config L55, spec L607 | `modis_viirs_ndvi: implemented: False`. Hors périmètre §15. |
| 12 | **Landsat** (imagerie multispectrale) | **MENTIONNÉE** | `pipeline/config.py`, `BACKEND_FIELD_SHIFT.md` | config L56, spec L607 | `landsat: implemented: False`. Hors périmètre §15. |
| 13 | **ECOSTRESS** (température canopée / ET) | **NON UTILISÉE** | — | — | Absent du dépôt. Non mentionné dans la spec. |
| 14 | **SRTM** (topographie, altitude) | **NON UTILISÉE** | — | — | L'altitude est lue directement dans `geometry.coordinates[2]` de la réponse NASA POWER (§6.1, fetch L133). Pas besoin de SRTM en plus. |
| 15 | **GAEZ** (aptitude des zones agro-écologiques, FAO) | **NON UTILISÉE** | — | — | Absent du dépôt. |
| 16 | **GLDAS** (bilan hydrique / humidité sol modèle global) | **NON UTILISÉE** | — | — | Absent du dépôt. |
| 17 | **NLDAS** (bilan hydrique États-Unis) | **NON UTILISÉE** | — | — | Absent du dépôt. Non applicable au Togo (voir §3.8). |
| 18 | **GEDI** (structure forêt, hauteur canopée) | **NON UTILISÉE** | — | — | Absent du dépôt. |
| 19 | **ERA5 / ERA5-Land** (réanalyse ECMWF) | **MENTIONNÉE** | `scripts/fetch_historical_weather.py` | L52 | Citée comme source sous-jacente d'Open-Meteo (`"Open-Meteo Historical Weather API (ERA5/ERA5-Land/Best Match)"`). Pas utilisée directement. |
| 20 | **Sentinel-2** (imagerie optique haute résolution, ESA) | **NON UTILISÉE** | — | — | Absent du dépôt. |
| 21 | **OpenET** (ET estimée par ensemble de modèles satellite) | **NON UTILISÉE** | — | — | Absent du dépôt. Couverture Afrique subsaharienne partielle. |
| 22 | **Open-Meteo Historical Weather API** | **MENTIONNÉE** | `pipeline/config.py`, `scripts/fetch_historical_weather.py`, `docs/sources_et_provenance.json` | config L48-51, script complet, sources L8 | Enregistrée `implemented: False` dans `SOURCES`. Script de secours présent mais non intégré au pipeline. `source_type: public_historical_reanalysis`. |
| 23 | **Zone « Kpalimé »** (lat=6,9000 lon=0,6333) | **UTILISÉE** | `data/zones.json`, `data/seed/zones.json`, tous les paquets et le golden | zones L14-15, paquets L1, golden L29,2195 | Coordonnées actives du projet pour la zone `plateaux_kpalime`. Présentes dans 20+ fichiers du dépôt. |
| 24 | **Zone « Atakpamé »** (lat=7,53 lon=1,13) | **NON UTILISÉE** | — | — | Absent de tout fichier du dépôt. Coordonnées du script de téléchargement externe uniquement (`scripts/telecharger_donnees_nasa_togo.py`, à ajouter). |

---

## Étape 2 — Vérifications sur le script externe (`scripts/telecharger_donnees_nasa_togo.py`)

> Ces vérifications portent sur le script à ajouter, **pas** sur le pipeline existant. Rien n'est corrigé.

### V-1 — Unité de `ALLSKY_SFC_SW_DWN` : libellé à corriger dans le rapport

**Ce que fait le pipeline existant (`fetch_power.py`) :**
- Accepte deux unités : `"MJ/m^2/day"` et `"kW-hr/m^2/day"` (ligne 40).
- Si l'unité reçue est `kW-hr/m^2/day`, multiplie par 3,6 → stocke en MJ/m²/j (ligne 125-126).
- Le méta-fichier `.meta.json` enregistre `"radiation_units_used": "MJ/m^2/day"` et `"ALLSKY_SFC_SW_DWN": "MJ/m^2/day"` (confirmé sur les 3 zones).
- La colonne finale s'appelle `rs_mj` : libellé **correct**.

**Ce que dit la documentation NASA POWER :**
L'unité native de l'endpoint `/temporal/daily/point` pour `ALLSKY_SFC_SW_DWN` est **kWh/m²/jour** (`kW-hr/m^2/day` dans le JSON). Cela a été confirmé lors du téléchargement réel (les chunks bruts l'indiquent dans leur header).

**Verdict :**
- Le script externe étiquette la colonne `rayonnement_kwh_m2` : c'est l'unité **brute de l'API**, valide si et seulement si aucune conversion n'est appliquée.
- Si le script stocke la valeur brute sans ×3,6, il faut nommer la colonne `rayonnement_kwh_m2`.
- Si le script convertit (comme le pipeline), il faut nommer la colonne `rayonnement_mj_m2` ou `rs_mj`.
- **Le pipeline Field Shift est correct.** Le script externe doit clarifier lequel des deux cas s'applique. L'ambiguïté est dans le libellé, pas dans la conversion.
- **Ne touche pas au contrat** (colonne interne, absente des paquets JSON).

### V-2 — Zone « plateaux » : Atakpamé vs Kpalimé

| Élément | Coordonnées | Source |
|---|---|---|
| **Projet** (actif dans 20+ fichiers) | lat=6,9000 lon=0,6333 → Kpalimé | `data/zones.json` L14-15, `data/seed/zones.json`, tous les paquets, golden |
| **Script externe** (à ajouter) | lat=7,53 lon=1,13 → Atakpamé | `scripts/telecharger_donnees_nasa_togo.py` |

**Verdict :**
- Les deux villes sont dans la région des Plateaux mais à ~80 km l'une de l'autre, avec des altitudes et des régimes pluviométriques différents.
- Changer les coordonnées invaliderait le golden et le contrat frontend.
- **Ne rien modifier** : c'est une décision à prendre explicitement avec le porteur du projet.
- Si le script externe doit être intégré un jour, utiliser `(6,9 ; 0,6333)` pour cohérence avec le projet.

### V-3 — EVLAND ≠ ET0 FAO-56

**EVLAND** (NASA POWER, paramètre GEOS-5) est l'évapotranspiration terrestre totale du modèle (W/m² ou mm/j selon la version). Elle inclut le sol nu, l'interception et la transpiration réelle — pas une ET0 de référence.

Le pipeline calcule l'ET0 FAO-56 Penman-Monteith (`pipeline/et0.py`) à partir de T2M, T2M_MAX, T2M_MIN, RH2M, WS2M, ALLSKY_SFC_SW_DWN et de l'altitude NASA POWER.

**Verdict :** Les deux grandeurs ne sont **pas interchangeables**. EVLAND ne doit jamais remplacer ni être additionnée à l'ET0 FAO-56. Son `source_type` honnête serait `nasa_power`, mais le moteur de bilan hydrique utilise exclusivement l'ET0 Penman-Monteith. Si EVLAND est téléchargée un jour, ce serait uniquement pour validation externe.

### V-4 — GWETROOT et GWETTOP non utilisés

Ces deux paramètres (humidité du sol normalisée 0-1, réanalyse MERRA-2) sont absents de `POWER_PARAMETERS` dans `pipeline/config.py`. Ils ne sont pas demandés à l'API et n'apparaissent dans aucun fichier du dépôt.

**Verdict :** Non utilisés aujourd'hui. Leur intégration éventuelle serait un champ de validation externe (voir §3), jamais un remplacement du bilan hydrique du moteur.

### V-5 — Période : 1991-2020 dans le script vs 1991-2025 dans le pipeline

| Élément | Période |
|---|---|
| **Pipeline** (`pipeline/config.py` L20-23) | `FETCH_START = "1991-01-01"`, `FETCH_END = "2025-12-31"` |
| **Script externe** | 1991-2020 (par défaut selon le document) |

**Verdict :** La tendance climatique (`trend`) compare 2016-2025 à 1991-2020. Sans les années 2021-2025, la tendance serait incalculable (D-30 : `null` si période récente non couverte). **Le script externe doit aligner sa période sur 1991-2025** pour être cohérent avec le pipeline. Cette correction ne touche pas au contrat.

### V-6 — Identifiants Earthdata : GPM_3IMERGDF et SPL3SMP_E

Ces identifiants désignent :
- **GPM_3IMERGDF** (v07) : précipitations journalières IMERG Final Run (NASA GES DISC).
- **SPL3SMP_E** : humidité du sol SMAP Enhanced, niveau 3 (NASA NSIDC DAAC).

**Verdict :** Ces deux produits nécessitent un compte Earthdata (earthdata.nasa.gov) et une approbation d'accès spécifique. Ils **ne peuvent pas être vérifiés sans téléchargement réel**. À vérifier sur le portail Earthdata avant tout usage. Ne pas lancer de téléchargement sans accord explicite du porteur du projet.

---

## Étape 3 — Décisions proposées

> **Règle générale :** aucune de ces propositions ne touche au code existant. Chacune est un ajout isolable. Les propositions marquées **(GO requis)** attendent un accord explicite avant implémentation.

### 3.1 — Sources hors périmètre §15 (IMERG, SMAP, MODIS/VIIRS, Landsat)

**Registre de sources extensible → déjà fait.**
`pipeline/config.py` contient déjà les entrées `gpm_imerg`, `smap`, `modis_viirs_ndvi`, `landsat` avec `implemented: False`. Conforme §15. Rien à ajouter en urgence.

**Script de validation externe → à créer (proposition réalisable au hackathon).**

| Source | Validation proposée | Sortie |
|---|---|---|
| **IMERG vs POWER (pluie)** | Comparer décadaires IMERG aux `precip_mm` POWER pour les 3 zones | `docs/validation_pluie_imerg.csv` + graphique |
| **SMAP vs SW simulé** | Comparer GWETROOT POWER (ou SMAP) au stock d'eau `SW` du moteur | `docs/validation_humidite_smap.csv` |

**Fichiers proposés :**
- `scripts/validate_rain_imerg_vs_power.py`
- `scripts/validate_soilwater_smap.py`

**Touche au contrat ?** **Non.** Ces scripts ne modifient ni les paquets ni l'API.

> **(GO requis)** pour le téléchargement réel d'IMERG et SMAP (compte Earthdata nécessaire).

### 3.2 — SRTM (topographie)

**Situation actuelle :** l'altitude est fournie par NASA POWER (`geometry.coordinates[2]`, fetch L133) et stockée par zone (`*.meta.json`, `elevation_m`). Valeurs réelles : ~255 m Kpalimé, ~40 m Lomé, ~340 m Kara.

**Proposition :** **Rien à faire maintenant.** SRTM serait utile pour une carte d'altitude régionale, mais le moteur n'a besoin que d'un seul point par zone. L'altitude NASA POWER est suffisante pour l'ET0.

**Touche au contrat ?** Non.

### 3.3 — ECOSTRESS (température de surface / ET)

**Proposition pour le hackathon :** Ajouter dans `pipeline/config.py` une entrée `ecostress` avec `implemented: False` et une note sur le potentiel de validation d'ET locale (résolution ~70 m, couverture irrégulière, ISS-based).

**Touche au contrat ?** Non — ajout dans le registre uniquement, pas dans les paquets.

### 3.4 — GAEZ (aptitude agro-écologique, FAO)

GAEZ v4 (FAO, libre) fournit des classes d'aptitude par culture au niveau sous-national pour le Togo, utiles pour vérifier la cohérence agronomique des zones pilotes avec les cultures `provisional_demo`.

**Proposition réalisable :** lire le fichier GAEZ v4 Togo et produire un tableau de comparaison `docs/gaez_aptitude_togo.md` pour les 5 cultures × 3 zones. **Pas d'intégration dans les paquets.**

**Touche au contrat ?** Non.

### 3.5 — GLDAS (bilan hydrique global)

GLDAS-2 (NASA GES DISC, 0,25°/~25 km) fournit humidité du sol, ruissellement et ET utiles pour comparer au stock d'eau `SW` du moteur.

**Proposition :** `scripts/validate_soilwater_gldas.py`, sortie rapport CSV. Téléchargement nécessite compte Earthdata.

**Touche au contrat ?** Non. **(GO requis)** pour le téléchargement.

### 3.6 — ERA5 / ERA5-Land

**Situation actuelle :** ERA5 est la source sous-jacente d'Open-Meteo (`scripts/fetch_historical_weather.py` L52). Le script de secours est présent mais `implemented: False`.

**Proposition réalisable sans compte :** activer `scripts/fetch_historical_weather.py` pour une période de validation (ex. 2015-2020) et comparer l'ET0 Open-Meteo (ERA5) à l'ET0 calculée par le pipeline POWER. Sortie : rapport CSV. Pas de compte requis (Open-Meteo est libre).

**Touche au contrat ?** Non — le script ne touche pas aux paquets.

### 3.7 — Sentinel-2 (NDVI, état de la végétation)

**Proposition hackathon :** trop long à intégrer proprement en J1. Ajouter dans `pipeline/config.py` une entrée `sentinel2_ndvi` avec `implemented: False`.

**Touche au contrat ?** Non.

### 3.8 — Sources USDA, USGS, PRISM, NLCD, NLDAS

**Verdict : NON APPLICABLE AU TOGO.**

| Source | Raison |
|---|---|
| PRISM | Couverture États-Unis uniquement. |
| NLCD (National Land Cover Database) | Couverture États-Unis uniquement. |
| NLDAS | Couverture États-Unis / Amérique du Nord uniquement. |
| USDA NASS | Statistiques agricoles États-Unis uniquement. |
| USGS StreamStats | Couverture États-Unis uniquement. |

Aucune de ces sources ne couvre l'Afrique de l'Ouest. Les mentionner dans ce rapport suffit.

### 3.9 — OpenET

**Situation actuelle :** non utilisé. OpenET fournit l'ET à partir d'un ensemble de modèles satellite (Landsat-based), couverture USA principalement. La couverture Afrique subsaharienne est partielle et en cours d'extension.

**Verdict :** Vérifier la disponibilité pour le Togo avant toute intégration. Non applicable au hackathon actuel.

---

## Étape 4 — Synthèse et impact sur le contrat

### Tableau des décisions

| Proposition | Fichier(s) | Priorité hackathon | Touche au contrat ? | GO requis ? |
|---|---|---|---|---|
| Libellé `rayonnement_kwh_m2` → clarifier conversion dans le script externe | `scripts/telecharger_donnees_nasa_togo.py` | **Haute** | **Non** | Non |
| Aligner la période du script externe sur 1991-2025 | `scripts/telecharger_donnees_nasa_togo.py` | **Haute** | **Non** | Non |
| Script validation pluie IMERG vs POWER | `scripts/validate_rain_imerg_vs_power.py` | Moyenne | **Non** | **Oui** (téléchargement IMERG) |
| Script validation humidité SMAP vs SW simulé | `scripts/validate_soilwater_smap.py` | Basse | **Non** | **Oui** (téléchargement SMAP) |
| Ajout entrées `ecostress`, `sentinel2_ndvi` dans `SOURCES` | `pipeline/config.py` | Basse | **Non** | Non |
| Tableau GAEZ aptitude Togo | `docs/gaez_aptitude_togo.md` | Basse | **Non** | Non |
| Script validation ET0 Open-Meteo (ERA5) vs ET0 POWER | `scripts/validate_et0_openmeteo.py` | Moyenne | **Non** | Non |
| NLDAS, PRISM, NLCD, USDA NASS : exclusion explicite | Rapport uniquement | — | **Non** | — |

### Points structurels à trancher avant toute implémentation

1. **Zone plateaux** : Kpalimé `(6,9 ; 0,6333)` ou Atakpamé `(7,53 ; 1,13)` pour le script externe ?
   - Le projet utilise Kpalimé dans **tous** les fichiers (paquets, golden, tests).
   - **Changer les coordonnées invalide le golden et le contrat frontend.**

2. **GWETROOT et GWETTOP** : validation externe uniquement, ou ajout dans `POWER_PARAMETERS` pour téléchargement comparatif hors pipeline ?
   - Disponibles via NASA POWER sans compte supplémentaire.
   - Ajout dans la liste de paramètres n'affecte pas les paquets si le CSV résultant n'est pas inclus dans le pipeline.

3. **Période du script externe** : aligner sur 1991-2025 est non bloquant et non-contractuel.

---

## Résumé exécutif

| Catégorie | Ressources | Verdict |
|---|---|---|
| **Utilisées et correctes** | PRECTOTCORR, ALLSKY_SFC_SW_DWN, T2M/MAX/MIN, RH2M, WS2M | Rien à faire. Pipeline conforme à §6.1 et §6.2. |
| **Registre déjà présent** | IMERG, SMAP, MODIS/VIIRS, Landsat, Open-Meteo | `pipeline/config.py` : `implemented: False`. Conforme §15. |
| **À valider en externe (sans toucher aux paquets)** | IMERG (pluie), SMAP/GWETROOT (humidité), ERA5/Open-Meteo (ET0) | Scripts proposés — GO requis pour IMERG/SMAP. |
| **Utile mais non urgent** | GAEZ, GLDAS, ECOSTRESS, Sentinel-2, OpenET | Documenter dans le registre. Pas d'intégration hackathon. |
| **Non applicable au Togo** | NLDAS, PRISM, NLCD, USDA NASS, USGS StreamStats | Exclusion explicite. |
| **Absents et non pertinents** | SRTM (altitude déjà dans POWER), GEDI (forêts) | Rien à faire. |
| **Alertes script externe** | Libellé unité, zone Atakpamé vs Kpalimé, période 1991-2020 | Signalées. Décisions au porteur du projet. |

> **Règle rappelée (§4)** : toute valeur de validation porte un `source_type` honnête et n'est jamais présentée comme une observation de parcelle.
> **Contrat frontend** (format du paquet §7, endpoints §10, `golden_cases.json`) : **inchangé** par toutes les propositions ci-dessus.

