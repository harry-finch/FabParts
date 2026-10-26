# Validation locale M5

La qualification s'applique à une **Part ou Collection**, à ses choix M4 et aux
fichiers réellement relus. Elle ne certifie pas l'ensemble du format KiCad ou CAO.
Les Asset gardent leur état global UNCHECKED ; les états de Part M1 ne changent pas.
Aucune génération, copie de bibliothèque officielle ou publication n'est effectuée.

## Parcours et politique

Sélectionner une Part ou Collection puis **Valider localement**. Exécuter les
contrôles pour enregistrer un rapport horodaté, avec version des règles `M5-1`,
empreinte, résultats et traces UUID/référence + SHA-256 des ressources contrôlées.
Une Collection agrège les résultats de tous ses composants ; les codes et messages
identifient le composant concerné. Ses rapports sont indépendants de ceux des Parts.

| État actuel | Qualification avant publication |
| --- | --- |
| UNCHECKED : aucun rapport | Refusée |
| STALE : rapport devenu obsolète | Refusée |
| ERROR : au moins une erreur | Refusée, même avec acceptation des WARNING |
| WARNING : aucun ERROR | Refusée tant que les WARNING ne sont pas acceptés |
| PASS : contrôles couverts satisfaits | Autorisée pour ce périmètre |

Pour accepter les WARNING : exécuter les contrôles, examiner le rapport, cocher
**J'ai examiné et j'accepte les WARNING de ce rapport**, puis relancer. Le service
exige un rapport préalable avec mêmes empreinte, règles et résultats. Une première
validation avec acceptation, ou une acceptation sur des données modifiées, est
refusée. L'acceptation est enregistrée avec le rapport ; la case UI est ensuite
remise à zéro. Une nouvelle validation sans acceptation remet celle-ci à zéro.

`LocalValidation.require_publishable(collection)` impose cette politique après
relecture. Il fournit une précondition pour M6 ; M5 ne produit aucune bibliothèque.

## Règles couvertes

| Contrôle | Résultat en cas d'échec ou de couverture partielle |
| --- | --- |
| Collection non vide ; Part non dépréciée | ERROR |
| Package associé, choix explicites SYMBOL sur Part et FOOTPRINT sur Package | ERROR |
| Asset choisi associé au bon propriétaire, type et fichier cohérents | ERROR |
| Fichier accessible, taille/hash conformes avant et après inspection | ERROR |
| S-expression UTF-8 équilibrée, racine/version reconnues, taille ≤ 64 Mio, profondeur ≤ 128 | ERROR |
| Symbole déterminé ; héritage local acyclique et résoluble, limité à 64 entrées | ERROR |
| Pins présents, numérotés, position/longueur finies et longueur non négative | ERROR |
| Pads électriques présents et numérotés, type reconnu, couche cuivre, position finie et dimensions positives | ERROR |
| Chaque numéro de pin présent parmi les pads électriques | ERROR |
| Pads électriques supplémentaires | WARNING |
| Nom du footprint différent du hint `Footprint` du symbole | WARNING |
| Liens 3D du footprint : nom présent, position/rotation finies, échelle positive | ERROR |
| Liens 3D déclarés sans modèle explicitement choisi sur Package | WARNING |
| Nom du modèle choisi différent des noms déclarés dans le footprint | WARNING |
| STEP/STP : enveloppe initiale et terminateur ; WRL : en-tête VRML 2 UTF-8 | ERROR si absent ; WARNING de géométrie non certifiée sinon |
| PDF sélectionné | Intégrité seule ; WARNING de contenu non certifié |
| Asset de provenance générée sélectionné | WARNING de révision humaine requise |

Les versions suivent les bornes KiCad 6–10 décrites dans [KICAD_INDEX.md](KICAD_INDEX.md).
Une version future non supportée est ERROR. Un fichier géré `.kicad_sym` doit
contenir une seule entrée racine : le choix M4 ne désigne pas une entrée interne.
Une référence officielle désigne son entrée ; l'héritage dans cette même bibliothèque
est pris en compte. Pins/pads de même numéro sont traités en ensembles, sans refus
systématique des répétitions légitimes. Les pads NPTH sont exclus de la comparaison.

La comparaison du hint de footprint porte sur son nom après le séparateur de
bibliothèque ; elle ne certifie pas le namespace. Les liens 3D sont comparés par
nom de fichier, sans résoudre les variables ou matérialiser les dépendances.
Les Package M1 ont nom, description et associations, sans dimensions géométriques :
M5 contrôle leurs choix et leur cohérence, pas un ajustement mécanique mesuré.

Un modèle 3D et une datasheet sont facultatifs ; leur sélection déclenche leurs
contrôles. Une collection sans 3D peut obtenir PASS si aucun lien 3D n'est déclaré.
Une enveloppe STEP ou un en-tête WRL valide ne prouve pas que la géométrie est lisible.

Les contrôles s'appuient sur la [documentation officielle des S-expressions KiCad](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/).

## Persistance et invalidation

Alembic `0004_validation_reports` ajoute une table indépendante avec un rapport
JSON par Part ou Collection, sujet exclusif et clés étrangères. Le dernier rapport
remplace le précédent pour ce sujet ; M5 ne fournit pas d'historique de rapports.
Les ressources gardent leurs UUID, fichiers, hashes, provenances et choix existants.
Un JSON illisible ou un sujet incohérent bloque la qualification jusqu'à revalidation.

L'empreinte canonique SHA-256 inclut métadonnées de Part/Package/Collection,
associations, choix, métadonnées des assets sélectionnés, inspections et version
des règles. Une modification pertinente, un fichier disparu/corrompu, un changement
de configuration rendant une référence inaccessible ou des résultats modifiés rend
le rapport STALE. L'acceptation précédente ne s'applique plus. Les quantités,
inventaires et localisations du stock indépendant ne l'invalident pas.

STALE est calculé par relecture, sans supprimer le rapport enregistré. Le bouton
**Vérifier si le rapport est toujours actuel** fait cette vérification. Le service
relit aussi avant qualification de collection. Les références officielles persistées
et la configuration suffisent : supprimer le cache d'index n'invalide pas un rapport
si les fichiers officiels et les entrées pertinentes sont toujours vérifiables.

## Limites assumées

PASS porte uniquement sur les règles ci-dessus. M5 ne vérifie pas toute la grammaire,
les types électriques des pins, les fonctions des signaux, la justesse des valeurs,
les graphiques, toutes les formes/drills de pads, les espacements ou règles DRC.
Les unités, dimensions, collisions et placement réels des modèles 3D ainsi que le
contenu PDF ne sont pas certifiés. Accepter un WARNING ne complète pas ces contrôles.

Les inspections sont synchrones et relisent les ressources : une grande collection
ou des bibliothèques partagées peuvent ralentir l'interface. Aucun réseau ni
installation KiCad n'est nécessaire pour qualifier des assets gérés. Une référence
officielle requiert ses fichiers locaux accessibles, toujours lus sans modification.

La base et les fichiers externes ne forment pas un instantané atomique. Un changement
pendant l'enregistrement peut laisser un ancien rapport, qui sera STALE lors de la
qualification suivante. Les fichiers peuvent aussi changer après le contrôle ; M5
ne garantit pas une publication immuable. M6 devra revérifier ses entrées au point
d'utilisation, puis M7 traitera les instantanés. Les règles futures doivent changer
la version de règles afin de ne pas réutiliser abusivement des rapports M5.

## Projection TECH-04B dans Tauri/Svelte

`ValidationReview` réutilise LocalValidation et les constats RESOURCE actuels.
L'éligibilité M5 définit Prêt pour PCB. Un symbole sélectionné dont l'intégrité et
la structure sont contrôlées peut être Prêt pour schéma malgré les erreurs PCB
sur le package, le footprint ou le mapping ; ses WARNING propres doivent avoir
été acceptés. Un rapport absent/STALE ne démontre aucune préparation. Ces statuts
ne modifient ni Part.state ni Asset.validation_state.

Une capacité de session lie l'acceptation au rapport WARNING exactement affiché.
Un rapport remplacé, une modification d'entrée ou un redémarrage invalide cette
confirmation. La politique M5 reste inchangée ; une validation neuve remet
l'acceptation à zéro. Les détails d'IPC, les bornes et la qualification native
figurent dans [TECH-04B](FABPARTS_2_TECH_04B.md).
