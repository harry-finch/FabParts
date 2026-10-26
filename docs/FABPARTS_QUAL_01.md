# QUAL-01 — Qualification fonctionnelle de bout en bout

26 octobre 2026 · `qual/01-end-to-end` · **GO WITH CONDITIONS**

## Base et environnement

La PR [TECH-05B #7](https://github.com/harry-finch/FabParts/pull/7), incluant
`ba8d7a3`, était sans conflit et sans contrôles CI publiés. Fusion par merge commit
`31f88fe44a9b069df440c0324e89eea16ac07882`, puis branche depuis ce main propre.
Checkout officiel et origin `harry-finch/FabParts` vérifiés.

Application Tauri réellement compilée et exécutée sur macOS ARM64, avec son sidecar
Python embarqué et FreeCAD disponible. KiCad graphique **10.0.7 ARM64**. Les rapports
TECH-03 à TECH-05B, AGENTS, les skills Fab Design System, Professional Workshop UI,
KiCad, vérification Python et checkpoint ont guidé cette passe ciblée.

Les données de qualification sont ignorées sous `local-data/qual01` : workspace
personnel jetable, corpus local, sauvegarde, publications, copie readonly, projet
KiCad et configurations dédiées. `FABPARTS_USER_DATA_DIR` et
`FABPARTS_KICAD_CONFIG_ROOT` désignent cet environnement. Avant le lancement de
KiCad, `KICAD_CONFIG_HOME`, `KICAD_DOCUMENTS_HOME` et `KICAD_CACHE_HOME` ont été
contrôlés ; les trois valeurs ont également été relues dans l'environnement du
processus graphique effectif. Aucun import des préférences personnelles KiCad.

## Références et ressources utilisées

Les neuf fichiers KiCad du corpus ont été copiés depuis les bibliothèques
officielles installées, puis vérifiés par SHA-256. L'index local de ce corpus
contient 2 239 références, sans problème signalé. Les trois composants ont été
créés dans l'interface native ; aucun composant n'a été prérempli dans la base.

| Référence créée | Collection / package | Ressources officielles choisies |
| --- | --- | --- |
| NE555D, Texas Instruments, MPN NE555D | LabParts / SOIC-8 3.9 × 4.9 mm, P1.27 | `Timer:NE555D`, `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm`, STEP correspondant |
| 10 kΩ 0603, composant générique sans fabricant ni MPN inventés | PersonalParts / R 0603 1608 métrique | `Device:R`, `Resistor_SMD:R_0603_1608Metric`, STEP correspondant |
| LM1117MP-3.3, Texas Instruments, MPN LM1117MP-3.3/NOPB | LabParts / SOT-223-3 TabPin2 | `Regulator_Linear:LM1117MP-3.3`, `Package_TO_SOT_SMD:SOT-223-3_TabPin2`, `SOT-223.step` |

La variante NE555D SOIC-8 a été vérifiée auprès de
[Texas Instruments](https://www.ti.com/product/NE555). Son
[PDF constructeur](https://www.ti.com/lit/ds/symlink/ne555.pdf), 39 pages, a été
importé par le sélecteur natif et conservé dans l'Asset Store. Le
[document LM1117](https://www.ti.com/lit/ds/symlink/lm1117.pdf) a servi à vérifier
la variante ; il n'a pas été associé au composant dans ce parcours. Les deux autres
cartes PDF signalent donc une absence réelle. Les bibliothèques et PDF téléchargés
ne sont pas ajoutés au dépôt ; les nouvelles fixtures de tests sont synthétiques.

## Parcours et résultats observés

| Parcours natif | Résultat |
| --- | --- |
| Création des trois références, métadonnées, collections, création de packages, sélection de candidats locaux | Réussi ; choix explicite de chaque ressource, puis enregistrement confirmé |
| Quatre cartes NE555D | Symbole à huit pins, empreinte à huit pads, rendu STEP et PDF page 1/39 visibles |
| Brouillon de résistance incomplet | Trois erreurs bloquantes détectées ; ajout du package et des ressources, ancien rapport STALE, puis requalification |
| WARNING et préparation | Consentement initialement vide ; acceptation explicite après lecture. NE555D : deux WARNING, résistance et LM1117 : un chacun ; statut prêt pour PCB ensuite |
| Redémarrage de FabParts | Les trois composants, associations, packages et acceptations persistent |
| Sauvegarde depuis Paramètres et données | Sauvegarde complète créée et vérifiée ; manifeste et contenu revérifiés en fin de passe |
| Qualification de LabParts, publication v1 | Deux composants, trois WARNING relus et acceptés ; résumé, confirmation explicite, publication engagée et intégrité vérifiée |
| Modification du libellé NE555D en `NE555D — QUAL v2` | MPN et ressources conservés ; rapports du composant et de LabParts STALE, requalification et acceptations renouvelées avant v2 |
| Publication v2 | Réussie et intégrité vérifiée ; v1 reste active, état « Mise à jour disponible » |
| Reconstruction historique v1 après v2 | Réussie depuis le sélecteur de dossier natif ; 19 fichiers historiques inchangés, reconstruction identique octet pour octet aux artefacts v1 |
| Activation v2, vérification, retour explicite à v1, vérification | Réussis ; nickname stable, copie installée v2 contenant le libellé de test, copie v1 contenant NE555D sans ce marqueur |
| KiCad : sélecteur global de symboles et sélecteur d'empreintes | Ressources FabParts trouvées ; huit pins/pads SOIC et pads 1/2/3 avec tab 2 du SOT-223 observés |
| Projet KiCad jetable | NE555D inséré comme U1, empreinte FabParts associée ; schéma enregistré puis rouvert. Mise à jour du PCB : zéro erreur, zéro avertissement ; PCB enregistré puis rouvert ; huit pads et chemin STEP confirmés sur disque |
| Vue 3D du PCB | Modèle SOIC chargé. L'avertissement de contour PCB absent est attendu pour ce projet d'insertion sans routage ni contour |
| Copie readonly de ce workspace | Python et sidecar embarqué lisent trois composants ; ingestion, acceptation de validation, publication et récupération d'intégration refusées avec READ_ONLY ; inventaire complet inchangé |

La modification des associations du brouillon de résistance vérifie le passage à
STALE après changement de ressources ; la modification du libellé NE555D vérifie
également l'invalidation des rapports composant et collection. Le libellé v2 est
un marqueur de qualification, pas une nouvelle identité électronique.

## Défaut corrigé et architecture

**P1 corrigé :** les aperçus de petits symboles officiels étaient refusés lorsque
leur bibliothèque complète dépassait 100 000 expressions (`Device` et
`Regulator_Linear`). L'héritage du LM1117 rendait ce cas particulièrement visible.

L'aperçu isole désormais le symbole sélectionné et ses ancêtres par positions
lexicales, avant allocation de leur arbre syntaxique. La structure du fichier
parcouru est contrôlée. Les limites de taille de fichier, profondeur, chaîne
d'héritage, expressions sélectionnées, dessins et primitives restent bornées.
Aucune ressource n'est réécrite. Les parseurs existants conservent leur API.
Le nouvel aperçu LM1117 a été vérifié dans le paquet natif reconstruit ; `Device:R`
a également été relu directement avec le service d'aperçu sur le fichier officiel.

Cinq cas de non-régression couvrent grande bibliothèque avec héritage, symbole
sélectionné lui-même excessif, ancêtre absent, cycle, doublon et fichier tronqué
(les quatre derniers sont paramétrés). Domaine, schéma SQLite, publications,
installation, workflows et système de thème inchangés.

## UX et réserves non bloquantes

Inspection native en FR/EN, clair/sombre, fenêtre normale et réduite : navigation,
assistant, qualification et publications restent accessibles ; défilement utilisable,
actions et états de version lisibles. Les quatre cartes permettent de contrôler
les associations avant enregistrement. Les limites de rendu et WARNING restent
explicites et n'ont pas été assimilés à une certification électrique ou mécanique.

Backlog P2, sans refonte dans ce jalon :

- Les noms exportés `FabParts_<UUID>`, `P_<UUID>` et `F_<UUID>` sont stables mais
  peu lisibles dans les sélecteurs KiCad. Les descriptions/valeurs aident ; les
  symboles de base nécessaires à l'héritage y sont également visibles.
- La recherche séparée des trois types de candidats demande plusieurs actions.
  Une amélioration doit préserver le choix explicite des variantes.
- Certains diagnostics techniques et messages déjà affichés conservent leur langue
  d'origine lors d'un changement FR/EN ; harmonisation ultérieure du contrat de
  traduction, sans masquer les informations de diagnostic.

Le sélecteur de reconstruction a temporairement présenté un bouton Open désactivé
pendant la navigation automatisée ; il s'est ensuite activé et la reconstruction
a réussi. Aucun défaut produit reproductible ni correctif de dialogue conclu.

## Sécurité des données et incident de manipulation

Un incident de l'outil de qualification doit être signalé : après fermeture de
l'instance de test, une inspection native a relancé FabParts sans les variables
d'isolation et créé un workspace personnel **neuf et vide** hors du dossier jetable.
Cette instance a été fermée ; zéro composant et aucun asset y ont été vérifiés.
Le dossier complet a été conservé sous
`local-data/qual01/unexpected-empty-default-workspace`, puis son absence initiale
à l'emplacement personnel a été rétablie. Il n'a pas été supprimé. La suite a
repris avec un lancement explicitement isolé. L'origine de la fermeture précédente
n'est pas attribuée à un crash produit : le journal indique une fermeture coopérative.

Il serait donc inexact d'affirmer que toutes les écritures du harnais sont restées
isolées. En revanche, l'inventaire final confirme :

- les 14 fichiers des préférences personnelles KiCad sont identiques au début ;
- les neuf fichiers de données personnelles KiPart Manager sont identiques ;
- le répertoire personnel FabParts, absent au départ, est de nouveau absent ;
- les anciens corpus TECH-05B native, KiCad et readonly sont inchangés ;
- les neuf sources officielles utilisées, les 19 fichiers historiques v1 et la
  copie installée v1 sont inchangés.

Une copie exacte préalable des préférences KiCad et les inventaires SHA-256 sont
conservés dans les données locales ignorées. Les lancements ultérieurs ne doivent
jamais utiliser l'auto-relance de l'outil d'inspection sur une application fermée.

## Vérifications automatisées

| Contrôle exécuté | Résultat |
| --- | --- |
| `PYTHONPATH=src FABPARTS_TEST_FREECAD=1 pytest -q` après correction | **593 passed** (588 avant correction) |
| Tests ciblés aperçus / parseur / index | **67 passed** |
| Ruff check et format check | Conformes ; 255 fichiers vérifiés pour le format |
| mypy | Conforme, 184 modules |
| `cargo +1.90.0 test --locked` | **32 passed** |
| `cargo +1.90.0 fmt --check` | Conforme |
| Frontend TECH : `npm test`, `npm run check` | **79 passed**, zéro erreur et zéro avertissement Svelte |
| Frontend UX : tests, Svelte check, build | **12 passed**, zéro erreur et zéro avertissement Svelte, build réussi |
| Sidecar + bundle Tauri `--bundles app` macOS ARM64 | Réussis après correction ; paquet exécuté pour les vérifications natives |
| `git diff --check` | Conforme |

Les suites couvrent ingestion/Asset Store, sauvegarde/restauration, validation,
immutabilité des publications, intégration, récupération et rollback. Les contrôles
Rust/frontends sont inchangés depuis la passe initiale ; la correction concerne
uniquement Python. Le build Vite conserve son avertissement de taille de chunks.

## Captures et décision

- [Quatre aperçus NE555D](qual01/ne555-four-previews.jpg).
- [Limite avant correction](qual01/regulator-preview-limit-before.jpg) et
  [LM1117 après correction](qual01/regulator-preview-fixed.jpg).
- [Publications et rollback v1, FR sombre](qual01/publication-rollback-v1.jpg).
- [Symbole global et empreinte SOIC](qual01/kicad-global-symbol-footprint.jpg),
  [sélecteur d'empreintes SOT-223](qual01/kicad-footprint-selector.jpg).
- [Schéma rouvert](qual01/kicad-schematic-reopened.jpg) et
  [modèle 3D du projet](qual01/kicad-project-3d.jpg).

**GO WITH CONDITIONS** : la chaîne réelle FabParts → publication → installation
→ projet KiCad fonctionne ; aucun P0/P1 produit connu ne subsiste dans le parcours
qualifié. Réserves : backlog UX ci-dessus et discipline de lancement du harnais
à respecter après l'incident documenté. Pas de qualification des autres versions
KiCad, autres systèmes, restauration native complète ni insertion des trois
références dans un même circuit. PersonalParts a été qualifié au niveau composant,
sans publication/installation de cette collection pendant cette passe.

QUAL-01 est proposé à revue par PR ; aucun merge automatique ni début de TECH-06.
