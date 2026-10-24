# Index KiCad local — M3

## Utilisation

L'onglet **KiCad local** permet de découvrir les dossiers installés ou de saisir
manuellement les racines `symbols`, `footprints` et `3dmodels`. Un dossier par type
est pris en charge ; un type peut rester vide. Les racines manuelles doivent
correspondre aux bibliothèques officielles que l'utilisateur souhaite consulter.
Leur authenticité n'est pas certifiée par l'application.

1. Cliquer **Découvrir les dossiers installés**, ou saisir les trois racines.
2. Enregistrer la configuration, puis **Reconstruire l'index local**.
   Reconstruire enregistre aussi les chemins affichés avant de scanner.
3. Rechercher un nom, une bibliothèque, une description ou des mots-clés ;
   choisir éventuellement un type. La recherche est une sous-chaîne littérale,
   insensible à la casse Unicode ; elle ne classe pas la pertinence. Une recherche
   vide affiche les premiers éléments, triés par clé stable, avec une limite de 200.

La découverte propose les premières racines existantes, par type : variables
`KICAD10_*` à `KICAD6_*` (`SYMBOL_DIR`, `FOOTPRINT_DIR`, `3DMODEL_DIR`), puis
emplacements standard macOS, `/usr/share/kicad`, `/usr/local/share/kicad`, ou
`ProgramFiles/KiCad/<10…6>/share/kicad` sous Windows. Les tables personnelles
`sym-lib-table` et `fp-lib-table` ne sont pas interprétées. Les chemins non standard
se configurent manuellement. Les variables pointant vers des dossiers absents
ne sont pas retenues par la découverte ; un chemin saisi absent est refusé.

Les chemins locaux normalisés sont conservés dans `config/kicad.toml` sous le
dossier de données. Aucun scan ni lancement de KiCad n'est fait au démarrage.
Une absence d'installation est normale : les sept onglets du catalogue et les
fichiers gérés restent utilisables. Un index absent est signalé.

La reconstruction utilise un thread Qt ; la recherche dans l'ancien cache reste
possible pendant le scan. Les champs et boutons de configuration sont bloqués
jusqu'à la fin. Attendre la fin du scan pour fermer la fenêtre ; il n'y a pas de
commande d'annulation dans M3. Une grande installation peut prendre plusieurs
dizaines de secondes, notamment pour lire les hashes des modèles 3D.

## Formats et compatibilité

Le lecteur de métadonnées cible les bibliothèques modernes KiCad **6 à 10**,
avec les bornes de version de fichier suivantes. Il s'agit de compatibilité
**d'indexation**, pas d'une certification de toutes les constructions KiCad.

| Ressource | Organisation et version prise en charge |
| --- | --- |
| Symboles | Fichiers `*.kicad_sym` directement sous `symbols` ; racine `kicad_symbol_lib`, version datée de `20211014` à `20251024` |
| Footprints | `*.pretty/*.kicad_mod` ; racine `footprint`, version datée de `20210108` à `20260206` ; nom interne identique au nom du fichier |
| Modèles 3D | Parcours récursif de `3dmodels` ; STEP/STP et WRL, extensions insensibles à la casse ; indexation de chemin et hash uniquement |

Fixtures testées : symboles 20211014/20220914/20231120/20241209/20251024 et
footprints 20210108/20221018/20240108/20241229/20260206. Intégration réelle :
KiCad 10.0.7 sur macOS arm64. Les installations 6–9 et les autres OS ne sont pas
qualifiés par un essai natif ; seuls les lecteurs de métadonnées sont testés sur
ces fixtures déterministes.

Les en-têtes utilisent des S-expressions, chaînes UTF-8 et versions YYYYMMDD,
selon les documentations officielles
[syntaxe](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/),
[symboles](https://dev-docs.kicad.org/en/file-formats/sexpr-symbol-lib/) et
[footprints](https://dev-docs.kicad.org/en/file-formats/sexpr-footprint/).
Le parsing est isolé dans l'infrastructure ; profondeur limitée à 128 et taille
S-expression à 64 Mio. Les champs graphiques et mécaniques sont parcourus pour
la structure, sans validation sémantique. Les unités imbriquées des symboles ne
créent pas d'entrées supplémentaires. Description, mots-clés et `extends` sont
conservés directement ; les propriétés héritées ne sont pas résolues en M3.

Versions hors bornes, UTF-8 invalide, syntaxe tronquée, identité invalide/dupliquée,
fichiers vides, `.lib` et `.mod` historiques sont signalés. Les fichiers de
support et extensions autres que celles indiquées ne sont pas indexés.
Les symlinks de fichiers sont signalés et ignorés ; un répertoire symlink provoque
un échec global explicite, sans suivre des chemins externes.

## Références et provenance

`KiCadReference` est une valeur distincte d'`Asset` et d'`AssetFile`.

- Symbole : `Device:R` ; le nickname de M3 est le nom du fichier bibliothèque.
- Footprint : `Resistor_SMD:R_0402_1005Metric` ; nickname issu du dossier `.pretty`.
- Modèle : `Resistor_SMD.3dshapes/R_0402_1005Metric.step`, relatif à `3dmodels`.

La clé est `kicad:<type>:<identifiant encodé URL>`. Aucun chemin d'installation
n'entre dans l'identité ; un déplacement conservant les noms conserve les clés.
Les nicknames de tables personnalisées ne sont pas pris en charge.

Chaque référence garde l'origine `KICAD_OFFICIAL`, son chemin relatif, la version
lue et SHA-256. Pour un symbole, le hash porte sur **toute la bibliothèque** ;
pour un footprint ou modèle, sur le fichier individuel. Ces hashes constatent les
octets lus, sans conférer une validation : les résultats sont affichés UNCHECKED.
Aucune copie officielle n'est créée dans l'Asset Store, ni associée à une Part.

## Cache et récupération

`index/kicad.sqlite3` est un cache indépendant de `database/catalogue.sqlite3`.
Son schéma interne versionné peut être supprimé/recréé ; il n'a pas de migration
Alembic et ne contient pas de donnée autoritative du catalogue. Sauvegarder la
configuration est utile ; sauvegarder le cache est facultatif.

Chaque reconstruction construit une nouvelle base temporaire complète, ferme et
synchronise le fichier, puis remplace atomiquement le cache. Les références et
signalements sont déterministes pour les mêmes sources. Une configuration
changée est signalée tant que le cache n'a pas été reconstruit.

Une erreur de fichier produit un index partiel accompagné des signalements
persistés, visibles dans l'onglet. Une erreur globale de parcours, de contrainte,
d'écriture ou de remplacement conserve l'ancien cache. Une racine absente ou une
configuration vide empêche le scan. Un cache corrompu ou incompatible est signalé
et se répare par reconstruction explicite. Une configuration TOML invalide peut
être remplacée en ressaisissant les chemins dans l'interface.

Après un arrêt brutal, un temporaire non référencé peut rester dans `index/` ;
seul `kicad.sqlite3` est consulté. Aucune surveillance automatique des mises à jour
KiCad n'est fournie : reconstruire après changement d'installation. Un cache
existant peut donc décrire des fichiers disparus ou modifiés ; son hash ne garantit
pas leur disponibilité future. Le catalogue et le store restent indépendants.
