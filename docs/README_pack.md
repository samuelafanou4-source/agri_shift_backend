# AGRI SHIFT — Pack de données provisoires

Pack conçu pour tester le moteur de rotation des cultures, avec une séparation stricte entre exemples synthétiques et données historiques publiques.

## Démarrage rapide
1. Utiliser `data/synthetic/` pour tester immédiatement l'interface et les règles.
2. Installer une version récente de Python (3.9+).
3. Depuis ce dossier, lancer par exemple:
   `python scripts/fetch_historical_weather.py --start 2023-01-01 --end 2023-12-31`
4. Les fichiers téléchargés apparaîtront dans `data/historical/`.
5. Avant une démonstration, vérifier les dates, les unités, les métadonnées de source et la présence des avertissements.

Le script appelle Open-Meteo au moment où vous l'exécutez. Aucune observation historique n'a été fabriquée ni incluse dans les fichiers synthétiques.

## Règles importantes
- Ne jamais présenter `synthetic_demo`, `provisional_demo` ou `synthetic_scenario` comme données observées.
- Les scores de rotation sont des scores de test, pas des rendements estimés.
- Valider les cycles, calendriers, besoins hydriques et règles auprès de sources agronomiques locales avant un usage de terrain.
- Pour le jour du hackathon, garder le schéma de données stable et remplacer la source par le connecteur NASA choisi, après vérification de l'énoncé officiel et des règles.
