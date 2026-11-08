# Dictionnaire des données — AGRI SHIFT

## Statuts de provenance
- `public_historical_reanalysis`: téléchargé depuis une API publique d'historique météorologique (Open-Meteo archive API); modèle/réanalyse, pas observation directe de parcelle.
- `synthetic_demo`: valeur inventée pour tests fonctionnels uniquement.
- `provisional_demo`: valeur ou règle provisoire à faire valider; ne pas afficher comme recommandation scientifique validée.
- `synthetic_scenario`: scénario hypothétique, pas prévision.

## Fichiers
- `data/zones.csv` / `.json`: trois points de référence géographiques approximatifs.
- `data/cultures.csv` / `.json`: catalogue provisoire de cinq cultures.
- `data/regles_rotation.csv` / `.json`: règles explicables avec scores fictifs.
- `data/synthetic/climat_synthetique.csv` / `.json`: valeurs météo entièrement synthétiques.
- `data/synthetic/parcelles_demo.csv` / `.json`: profils de parcelles fictifs.
- `data/synthetic/scenarios.csv` / `.json`: scénarios de stress-test.
- `data/historical/`: reçoit les données réelles de réanalyse après exécution du script de collecte.

## Unités
- `precipitation_mm`: millimètres par jour.
- `temperature_*_c`: degrés Celsius.
- `et0_mm_day`: évapotranspiration de référence en millimètres par jour.
- `cycle_days_demo`: durée de cycle en jours, indicative.
- `area_ha`: hectares.
- `rainfall_change_pct`: variation relative de précipitations en pourcentage.
- `temperature_change_c`: variation hypothétique de température en °C.

## Sources publiques
1. Open-Meteo Historical Weather API: https://open-meteo.com/en/docs/historical-weather-api
2. Endpoint d'archive: https://archive-api.open-meteo.com/v1/archive
3. FAO GIEWS Togo: https://www.fao.org/giews/countrybrief/country.jsp?code=TGO&lang=en
4. SoilGrids (pour une extension sols; vérifier la disponibilité de l'API avant intégration): https://soilgrids.org/

## Limites
- Les trois coordonnées sont des points de référence, pas des limites administratives précises ni des parcelles.
- Les données de réanalyse représentent une maille de modèle; elles ne décrivent pas nécessairement les conditions exactes d'un champ.
- Les paramètres de cultures et règles de rotation sont provisoires et destinés à tester le moteur. Ils ne constituent pas un conseil agronomique.
- Les valeurs synthétiques ne doivent jamais être mélangées aux données réelles sans `source_type`.
- Les règles de rotation simplifiées ne modélisent pas les variétés, la pression des ravageurs/maladies, le calendrier précis, les intrants, le marché, la fertilité détaillée ni les préférences locales de manière exhaustive.
- Les données météo seules ne permettent pas de prédire de façon fiable un rendement agricole.
