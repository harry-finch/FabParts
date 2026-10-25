# KiPart Manager — Architecture cible

## Statut et principes

Architecture cible ; M0 a créé le socle et M1 a ajouté les sept entités initiales,
le catalogue applicatif, la persistance SQLite et les formulaires. M2 ajoute
l'Asset Store et l'import/restitution. M3 ajoute l'index officiel local, M4 le
resolver et M5 les rapports de validation. M6 ajoute la construction des
bibliothèques ; M7 ajoute les publications immuables ; M8 ajoute le transfert
portable. Le MVP est complet ; M9 ajoute la recherche officielle distante
optionnelle. M10 ajoute identification traçable et fiches PDF locales avec
téléchargement constructeur facultatif. M11 ajoute l’assistance d’identification facultative ; M12+ reste à implémenter.
Voir [PROJECT_SPEC.md](PROJECT_SPEC.md) pour les invariants produit et
[MILESTONES.md](MILESTONES.md) pour leur introduction progressive.

Le système est local-first et suit une architecture pragmatique en couches et
ports/adapters. Préférer des abstractions métier petites à un framework générique.

## Couches et dépendances

Le parcours conceptuel des opérations est UI → Application → Domain → Ports
→ Infrastructure. Cette notation décrit les responsabilités et l'exécution ;
elle ne prescrit pas une chaîne d'imports du domaine vers l'infrastructure.
Les adaptateurs implémentent les contrats des ports, avec inversion de dépendances.

| Couche | Responsabilités | Dépendances autorisées |
| --- | --- | --- |
| UI | Vues PySide6, saisie, présentation des candidats et résultats | Application ; types métier nécessaires à la présentation |
| Application | Cas d'usage, orchestration, frontières transactionnelles | Domain et Ports |
| Domain | Entités, valeurs, invariants, transitions et décisions métier | Bibliothèque standard Python ; aucune dépendance aux adaptateurs |
| Ports | Contrats de persistance, stockage, indexation et autres capacités introduites au besoin | Domain et bibliothèque standard ; aucune implémentation concrète |
| Infrastructure | SQLite/SQLAlchemy, Alembic, filesystem, parsing KiCad, configuration ; adaptateurs optionnels futurs | Ports et Domain ; bibliothèques techniques nécessaires |

Un point de composition assemble les adaptateurs et les injecte dans les cas
d'usage. Il est le seul endroit où l'assemblage connaît leurs implémentations.
L'UI n'accède pas directement à la base ou au filesystem. Le domaine ne dépend
ni de PySide6, SQLAlchemy, HTTP, IA, filesystem concret, ni d'une installation KiCad.
Les détails des ports seront fixés à mesure des besoins ; ne pas créer de contrats
spéculatifs pour les milestones futures.

Structure créée en M0 :

```text
src/kipartmanager/
  domain/
  application/
  ports/
  infrastructure/
  ui/
tests/
```

Baseline : Python 3.12+, PySide6, SQLite, SQLAlchemy 2, Alembic, pytest,
typage statique, configuration TOML, SHA-256 ; ZIP + JSON pour `.kiparts` en M8.
Les dépendances sont ajoutées quand la milestone les nécessite. Aucune dépendance
lourde de CAO, telle qu'OpenCascade, n'est justifiée à ce stade.

## Modèle métier

- Part : identité UUID d'une référence catalogue, description et cycle de vie.
- Package : identité mécanique distincte, partageable entre Parts.
- Asset : identité logique, type, provenance et état de validation ; les octets
  sont conservés par l'Asset Store pour les ressources gérées.
- Inventory / StockItem / Location : gestion des quantités et emplacements,
  sans conditionner l'existence ni la publication des Parts.
- Collection : sélection de Parts destinée à KiCad, indépendante des inventaires.
- Publication : instantané reproductible d'une collection ; une version publiée
  est immuable, et ses associations ne suivent pas les modifications du catalogue.

Les liens Part → symbole/datasheet/Package et Package → footprint/modèle 3D
expriment des associations, pas une propriété exclusive des fichiers.
L'association footprint → modèle 3D conserve sa cohérence mécanique.
Les modèles ORM restent distincts des objets et règles du domaine.

Lab et Personal sont les inventaires initiaux ; LabParts et PersonalParts sont
les collections initiales. Leur présence ne crée pas de couplage entre stock et
publication. Les transitions de Part sont définies dans le domaine, avec leurs
préconditions introduites dans les milestones qui les rendent opérantes.

## Sources de vérité et stockage

Organisation conceptuelle du dossier de données, configurable et distinct du
dossier des sources :

```text
KiPartManager/
  database/
  assets/
  index/
  publications/
  exports/
  config/
```

| Donnée | Autorité et comportement |
| --- | --- |
| SQLite | Catalogue courant, associations, stocks et métadonnées gérées |
| Asset Store | Fichiers canoniques gérés, intégrité SHA-256 et déduplication de contenu |
| Manifests M7 | Description figée des versions publiées, dépendances et hashes |
| Index KiCad | Cache local reconstruisible ; jamais source de vérité du catalogue |
| Bibliothèques produites | Artefacts reconstruisibles depuis l'état décrit et ses dépendances |
| Exports | Paquets de transfert ; ne remplacent pas la base et le store locaux |

Les manifests font autorité sur l'état historique publié, sans remplacer
SQLite et l'Asset Store comme autorités du catalogue courant. Une reconstruction
requiert les octets correspondant aux hashes : une référence externe seule ne
garantit pas leur disponibilité après une mise à jour de KiCad. M7 devra fixer
la conservation ou la matérialisation nécessaire à la reproductibilité.

L'application orchestre la cohérence entre opérations de base et fichiers via
les ports ; l'infrastructure implémente les mécanismes concrets. Les stratégies
de staging, récupération après interruption et transactions seront définies en
M2, M7 et M8 selon leurs besoins. Les schémas évoluent par migrations Alembic.

## Références KiCad et managed assets

Une référence KiCad externe comporte une identité de bibliothèque et de ressource,
une origine et les informations nécessaires à sa résolution locale. Le chemin
d'installation est une information de cette machine, pas une identité portable.
Les identifiants et versions de M3 sont décrits dans [KICAD_INDEX.md](KICAD_INDEX.md).

Un managed asset contient un fichier contrôlé par le store, une empreinte et une
provenance. Une copie officielle matérialisée garde KICAD_OFFICIAL comme origine,
ainsi que son identité source ; elle ne devient pas USER_PROVIDED.
La déduplication d'octets n'efface pas les identités, provenances ou associations.

Les bibliothèques officielles sont toujours en lecture seule. Ne pas les copier
systématiquement dans le store : matérialiser seulement lorsque le mode de
publication/export demandé l'exige. Le mode portable M8 doit soit inclure les
dépendances nécessaires, soit définir une exigence portable explicitement
vérifiable ; son critère d'acceptation exige une bibliothèque complète utilisable
sans les chemins de la machine source. La politique exacte sera décidée en M6–M8.

## Résolution, validation et publication

Les cas d'usage interrogent les sources autorisées par la milestone. M4 recherche
dans les assets utilisateur, le catalogue géré puis l'index officiel local ;
il expose les candidats et laisse un choix explicite. Un candidat officiel ne
remplace jamais silencieusement un asset utilisateur.

Le parsing des formats et l'accès aux installations résident dans l'infrastructure.
Les décisions de compatibilité et de publication appartiennent au domaine ;
l'application agrège les résultats et orchestre les opérations.
M5 introduit PASS/WARNING/ERROR et les règles applicables. ERROR bloque M6.

M6 produit une bibliothèque KiCad exploitable depuis une collection validée.
Il s'agit de la construction des artefacts ; M7 ajoute l'engagement d'une version
immuable et son manifest. M6 n'anticipe pas le système de versions.
En M7, changer la collection ou ses assets ne modifie jamais une ancienne version.
M8 transporte une version et ses dépendances dans un ZIP avec manifest JSON.

Les paths des artefacts portables sont relatifs ou utilisent des références
KiCad portables documentées. Les chemins absolus locaux restent dans la
configuration ou les informations de résolution propres au poste.

## Adaptateurs futurs et garanties hors ligne

Le réseau, l'IA et la distribution ne sont introduits qu'à partir de leurs
milestones respectives, comme adaptateurs optionnels. Leur absence, un défaut
de configuration ou une panne ne bloque ni le démarrage ni les cas d'usage locaux.
Le serveur distribue ; il n'est jamais la source de vérité indispensable.

La génération future cherche d'abord les ressources existantes, puis utilise
une représentation structurée validable et un générateur déterministe. Les assets
générés conservent leur provenance et nécessitent une validation explicite.

## Vérification et décisions différées

Les tests utilisent des données jetables. Ils couvrent les règles métier sans
adaptateurs, les contrats de persistance/stockage et les parcours locaux pertinents.
Les tests de formats KiCad utiliseront des fixtures déterministes et des fichiers
représentatifs des versions supportées. Chaque checkpoint exécute toute la suite
alors configurée et s'arrête. M0 dispose de tests d'import, de points d'entrée,
de frontières architecturales et de lancement/fermeture Qt hors ligne.

Le point de composition est `bootstrap.py` à la racine du package ; il n'est
pas un cas d'usage de la couche Application. Il initialise Qt seulement au
lancement GUI. M1 y assemble le moteur SQLite, les migrations, le repository,
le catalogue applicatif puis la fenêtre. setuptools construit le
package ; Ruff assure lint/formatage et mypy le typage strict. Les versions
vérifiées sont figées dans `requirements-dev.lock` ; la configuration des outils
réside dans `pyproject.toml`.

## Décisions M1

- Entités dataclasses immuables dans `domain/entities.py`, UUID stables et
  transitions initiales DRAFT → IDENTIFIED → DEPRECATED ; DRAFT → DEPRECATED
  est aussi autorisé. Un nouvel enregistrement commence en DRAFT. Les autres
  états du cycle cible seront introduits avec leurs opérations futures.
- `application/catalogue.py` résout les références et appelle les règles du domaine
  pour les rôles d'assets, transitions et absence de liens dupliqués. Le contrat
  `ports/catalogue.py` couvre uniquement les sept types présents.
- Part possède zéro ou un Package ; Package est partageable. Part et Package
  ont chacun zéro ou plusieurs associations d'assets réutilisables. Une Part
  associe SYMBOL/DATASHEET ; un Package associe FOOTPRINT/MODEL_3D. Les liens
  directs footprint → 3D et la sélection d'un candidat principal sont différés.
- Collection ↔ Part est une relation plusieurs-à-plusieurs indépendante des
  stocks. Les associations sont des ensembles sans ordre, représentés par des
  tuples d'UUID triés pour un aller-retour stable.
- StockItem est unique par `(part_id, inventory_id)` ; quantité entière de
  0 à 2⁶³−1 ; zéro ou une Location. Les localisations sont globales, sans
  hiérarchie. Répartir un stock entre plusieurs emplacements reste hors M1.
- Les noms des inventaires, localisations et collections sont uniques dans leur
  type (comparaison SQLite sensible à la casse) ; ceux des Parts/Packages/Assets
  ne sont pas des identifiants uniques. Les noms sont requis et débarrassés des
  espaces aux extrémités.
- SQLAlchemy conserve des mappings distincts et trois tables d'association.
  Chaque sauvegarde et l'initialisation des valeurs par défaut sont transactionnelles.
  Une erreur de contrainte annule la sauvegarde entière. Les clés étrangères
  SQLite sont activées pour chaque connexion ; PK/FK/UNIQUE/CHECK sont nommées.
- La révision Alembic `0001_catalogue` est autonome, embarquée dans le package
  et exécutée au démarrage ; le code de production n'appelle pas `create_all`.
  Le downgrade destructif n'est testé que sur des bases jetables ; aucun
  downgrade automatique de données utilisateur n'est prévu.
- Lab/Personal et LabParts/PersonalParts ont des UUID de seed déterministes.
  Une nouvelle initialisation conserve leurs modifications et ne recrée pas
  un nom ancien après renommage. Les autres entités utilisent UUID4.
- L'UI utilise seulement le catalogue et les types métier. Les UUID des widgets
  sont des chaînes converties à la frontière de l'UI pour éviter les comparaisons
  QVariant/Python. `--data-dir` choisit la racine ; sinon Qt fournit le dossier
  de données du poste. Aucun chemin local n'est destiné à un artefact publié.
- En M1, Asset conserve type, origine, référence/source et état UNCHECKED sans
  fichier. M2 complète ce modèle par une association facultative à un fichier géré.

## Décisions M2 — Asset Store

- `AssetFile` est une valeur du domaine : SHA-256, taille, extension et nom original
  simple. Son identité de contenu produit une clé relative
  `blobs/<deux premiers caractères du hash>/<hash>`. Aucun path local concret
  n'est nécessaire au domaine.
- `ports/asset_store.py` définit import, vérification et restitution avec des
  locators de source/destination opaques. `application/asset_imports.py` orchestre
  ces opérations et le catalogue ; seul l'adaptateur local utilise pathlib/os.
- Le store copie par blocs de 1 Mio dans `assets/.staging/`, calcule le hash et
  la taille, synchronise le fichier, puis publie par lien physique exclusif.
  Un blob existant est réutilisé uniquement après contrôle d'intégrité. Aucune
  opération n'écrase un contenu canonique ou une destination de restitution.
- La source est seulement lue et doit rester stable pendant la copie. Les fichiers
  vides, extensions inconnues, chemins canoniques traversant des symlinks et
  destinations à l'intérieur du store sont refusés. La restitution est copiée
  dans un temporaire près de sa destination, contrôlée puis publiée exclusivement.
- Chaque asset garde une association facultative à `asset_files`, introduite par
  la révision `0002_asset_files`. La migration ajoute seulement une table et
  conserve toutes les données et relations M1. Les contraintes vérifient UUID/FK,
  hash, taille, extension et nom de fichier ; plusieurs assets peuvent référencer
  le même hash sans fusion de provenance.
- Un asset déjà lié à un fichier ne peut ni changer de fichier ni le détacher.
  L'application et le repository protègent cette association. L'éditeur de
  métadonnées conserve le fichier ; son type doit rester compatible avec le format.
- Le blob complet est publié et vérifié **avant** la transaction SQLite de l'asset.
  Il n'existe pas de transaction atomique commune au filesystem et à SQLite.
  Un échec avant commit laisse au plus un blob orphelin, jamais un import confirmé
  vers un fichier incomplet. Il est conservé et réutilisable ; aucun rollback
  filesystem ne supprime un blob qui pourrait être partagé par un autre asset.
- Une fin brutale pendant la copie peut laisser un temporaire non référencé ;
  il est ignoré au redémarrage. Un nouvel import repart d'un nouveau temporaire.
  Les erreurs normales nettoient leur propre temporaire. Les temporaires/orphelins
  ne sont pas supprimés automatiquement pour préserver les opérations concurrentes.
- Vérifier l'intégrité contrôle taille et SHA-256, sans changer UNCHECKED.
  Un fichier absent ou corrompu bloque la restitution et sa réutilisation comme
  doublon ; il n'est pas réparé silencieusement. Les modifications externes au
  store restent détectées à l'utilisation, pas par un audit continu.
- Les formats sont conservés comme octets opaques, sans interprétation PDF/CAO/KiCad
  ni génération. Des fichiers KiCad officiels locaux ont été consultés en lecture
  seule pour contextualiser les fixtures ; ils ne sont ni indexés ni copiés en masse.
- Le backend exige des liens physiques sur le volume du store et celui de la
  destination ; il signale les erreurs sans fallback d'écrasement. Sur POSIX,
  fichiers et répertoires sont synchronisés avant confirmation ; ces garanties
  ne constituent pas une certification contre toute panne matérielle.

## Décisions M3 — Index externe

- `KiCadReference` est distinct d'Asset/AssetFile ; son identité est type + nickname
  et entrée pour symbole/footprint, ou chemin relatif pour modèle 3D. Le chemin
  d'installation reste dans `LibraryRoots`, configuration propre au poste.
- `KiCadLibraries` orchestre un port d'index ; découverte, TOML, parsing et scan
  en lecture seule sont des responsabilités de l'infrastructure. Aucun resolver,
  association catalogue ou matérialisation de fichier officiel n'est ajouté.
- Le cache SQLite indépendant dans `index/` se reconstruit par staging/remplacement
  atomique. Il utilise un schéma interne versionné, sans migration Alembic : il est
  jetable et ne change pas les tables métier M1/M2. Les erreurs de fichiers sont
  persistées avec l'index partiel ; les erreurs globales préservent l'ancien cache.
- Un seul dossier par type est configurable. La découverte est locale, sans
  exécution KiCad, réseau ou scan automatique au démarrage. Le scan explicite
  fonctionne dans un thread Qt ; la fermeture attend sa fin.
- Les lecteurs ciblent les métadonnées KiCad 6–10 dans les bornes documentées ;
  hashes des fichiers lus, provenance et `extends` sont conservés. Les propriétés
  héritées, tables personnalisées et validation sémantique restent différées.
  Les références ne garantissent pas la disponibilité des octets après mise à jour.

## Décisions M4 — Choix locaux

- `LocalResolver` agrège les assets utilisateur, les autres assets gérés puis
  l'index local. Les candidats gardent leur identité/provenance et ne sont jamais
  fusionnés par hash. Une recherche ne modifie ni sélection ni état de Part.
- `ResourceChoice` désigne soit un UUID d'Asset, soit une `KiCadReference` externe.
  Un choix par rôle : SYMBOL/DATASHEET sur Part ; FOOTPRINT/MODEL_3D sur Package
  partagé. L'UI permet ce parcours mécanique depuis la Part associée au Package.
- Alembic `0003_resource_choices` ajoute une table sans réécrire les données
  existantes. Choix officiel stocké en instantané JSON portable, indépendant du
  cache M3 ; aucun blob ou Asset officiel n'est matérialisé. Choix géré et ajout
  d'association sont enregistrés atomiquement dans la même transaction.
- L'application exige une confirmation explicite de remplacement et un choix
  attendu. L'adaptateur compare ce choix sous `BEGIN IMMEDIATE`, également utilisé
  pour les sauvegardes catalogue afin de protéger les associations sélectionnées.
- Un choix géré requiert un fichier vérifié ; un choix officiel requiert une
  référence indexée identique et un fichier local de hash identique. L'erreur
  conserve les choix précédents et ne remplace aucun fichier. Les résultats sont
  UNCHECKED ; cohérence électrique/mécanique et états supplémentaires restent M5+.

Voir [LOCAL_RESOLVER.md](LOCAL_RESOLVER.md) pour les interactions, la persistance
et les limites. Les liens footprint → modèle 3D restent différés.

Restent à confirmer : modes de publication
et gestion des dépendances (M6), format des manifests et reproductibilité (M7),
conflits d'import et compatibilité portable (M8). Ces décisions doivent préserver
les invariants de la spécification et d'AGENTS.md.


## Décisions M5 — Qualification locale

- `domain.validation` porte résultats, agrégation, qualification et comparaison
  pins/pads. `LocalValidation` relit le catalogue et orchestre les ports
  `ResourceProbe` et `ValidationRepository`. Le parseur et les lectures de fichiers
  restent dans l'infrastructure ; Qt affiche les rapports via l'application.
- Les rapports qualifient une Part ou Collection, pas globalement chaque Asset.
  Les assets restent UNCHECKED et les états de Part M1 sont conservés. PASS décrit
  seulement les règles M5 couvertes ; la géométrie 3D et le contenu PDF restent
  non certifiés et signalés par WARNING.
- Alembic `0004_validation_reports` ajoute le dernier rapport JSON par sujet,
  avec clés étrangères et contraintes de sujet. Migration sans réécriture du
  catalogue ou des choix ; downgrade supprime seulement les rapports M5.
- L'empreinte canonique SHA-256 couvre métadonnées pertinentes, choix et faits
  extraits des fichiers vérifiés. Une qualification relit les entrées : différence
  d'empreinte, de règles ou de résultats rend le rapport STALE. Le stock indépendant
  ne participe pas à l'empreinte. L'ancien rapport reste consultable.
- L'acceptation des WARNING exige un rapport préalable identique et actuel.
  `require_publishable` refuse absence, STALE, ERROR ou WARNING non accepté.
  Cette précondition métier servira M6 ; aucun publisher n'est introduit.
- La qualification n'est pas atomique avec des fichiers externes. Une modification
  concurrente ne garantit pas un rapport actuel ; les consommateurs doivent
  revérifier avant utilisation. M5 ne promet pas d'instantané immuable.

Voir [VALIDATION.md](VALIDATION.md).

## Décisions M6 — Construction des bibliothèques

- `LocalPublisher` exige un rapport de Collection qualifié M5, capture un `BuildPlan`
  de valeurs du domaine, puis appelle le port `LibraryBuilder`. Le callback de
  confirmation revérifie qualification et plan avant/après exposition des sorties.
- `LocalLibraryBuilder` matérialise uniquement les ressources choisies, dans un
  nouveau dossier autonome. Aucune écriture dans SQLite, l'Asset Store, les sources
  officielles ou les tables globales ; aucun nouveau schéma ni dépendance.
- `kicad_writer` transforme des arbres issus des fichiers existants. Le parser M3
  conserve désormais guillemets et ordre mixte atomes/enfants pour éviter toute perte
  lors de la sérialisation. Symboles et parents d'héritage sont renommés ensemble ;
  les Package partagés produisent un seul footprint par collection.
- Un mode de copie autonome seulement ; les références externes restent des identités
  sources, pas des dépendances d'installation des sorties. Les tables et liens utilisent
  `${KIPRJMOD}`. Les modèles choisis doivent correspondre aux liens et transformations
  du footprint ; les cas ambigus sont refusés.
- Noms ASCII + UUID complets, modèles/PDF par hash. Sources inchangées + même état
  courant + même builder donnent les mêmes octets dans des dossiers neufs.
- Staging, réservation exclusive du dossier et installation par liens physiques
  exclusifs. BUILDING marque une opération incomplète. Les erreurs nettoient leurs
  sorties ; une interruption peut laisser un dossier non utilisable. M6 n'introduit
  ni version, manifest historique ni engagement atomique M7.

Voir [PUBLISHER.md](PUBLISHER.md) pour intégration KiCad, formats et limites.

## Présentation M6-UI

Le shell utilise une sidebar et QStackedWidget ; les pages du catalogue partagent
une liste filtrée et des détails contextualisés. La passe Professional Workshop
conserve cette structure et utilise désormais une palette sombre Fusion/QSS,
centralisée dans `ui/theme.py`, avec les composants de `ui/components.py`.
Les icônes Lucide locales et leur licence sont embarquées dans le package UI.
Les formulaires gardent un pied d'actions fixe et une zone de champs défilante.
Aucune dépendance, migration ni modification des couches métier n'est nécessaire.
Les appels aux use cases, contrôles M4/M5 et sorties M6 restent ceux de M6.
Les conventions effectives figurent dans [UI_GUIDELINES.md](UI_GUIDELINES.md).

## Décisions M7 — États historiques

- `domain.publication` porte l'identité de version et l'instantané. Le cas d'usage
  `Publications` exige M5 via `LocalPublisher`, capture le plan puis appelle le port
  `PublicationStore`. Les opérations historiques n'appellent pas le catalogue courant.
- `LocalPublications` conserve des manifests JSON canoniques, des copies d'inputs
  sélectionnés et des artefacts dans `publications/<UUID>/vNNNNNN`. Ces inputs font
  partie du stockage historique géré ; ils ne remplacent pas le catalogue/Asset Store
  courants et ne créent pas de fiche Asset officielle artificielle.
- Les manifests font autorité sur l'historique, comme prévu dans cette architecture.
  Aucun index SQL redondant : aucune modification persistante du schéma SQLite,
  donc aucune migration M7 nécessaire. Les versions ne suivent pas les éditions
  des Parts, Packages ou Collections.
- Un COMMIT contenant le hash du manifest est installé exclusivement en dernier.
  Les lecteurs ignorent les dossiers non engagés et refusent les manifests incohérents.
  Le staging, le contrôle final et l'exclusivité protègent les engagements concurrents.
- `FrozenBuilder` réutilise le writer M6 avec les seuls inputs historiques. Le moteur
  `M6-1` doit reproduire l'inventaire exact ou refuser la reconstruction. Les artefacts
  historiques peuvent être régénérés dans un dossier neuf sans modifier la version.
- La page Publications réutilise le socle M6-UI ; PUBLISHED distingue un
  manifest engagé d'une vérification d'intégrité PASS effectuée à cet instant.

Voir [PUBLICATIONS.md](PUBLICATIONS.md) pour format, engagement et garantie testée.


## Passe UI orientée tâches après M7

Les espaces Composants et Inventaire regroupent des outils secondaires via
QTabWidget ; la sidebar reste pilotée par QStackedWidget. `ui/component_panel.py`
présente une table et une fiche structurée. ResourceRow et WorkflowStrip sont des
widgets de présentation réutilisables. Les choix, qualifications, associations,
stocks et versions passent par les services existants ; aucune entité, repository,
migration, règle de qualification ou sortie de publication n'est modifiée.
Le guide UI et le bilan UX décrivent les limites de représentation.

## Transfert portable M8

Le cas d’usage Bundles dépend du port BundleTransport. LocalBundles adapte ZIP,
Asset Store, SqliteCatalogue et LocalPublications : contrôle préalable, transaction
SQLite unique et engagement exclusif de la version. Le manifest M7 reste inchangé.
La projection courante porte uniquement les données nécessaires à cette version ;
les stocks et qualifications courantes ne sont pas transférés.

Les références officielles sont matérialisées avec leur origine et un UUID stable
dérivé de leur clé/hash. AssetFile.symbol_name conserve le choix d’entrée dans un
fichier multi-symboles ; probe et builder utilisent ce sélecteur sans modifier les
bibliothèques officielles. La migration 0005_symbol_entry conserve les anciennes
données. Conflits, limites et récupération sont décrits dans [KIPARTS.md](KIPARTS.md).

## Recherche officielle distante M9

`RemoteLibraries` orchestre les ports `RemoteProvider`/`RemoteSettings`. Le domaine
porte configuration, candidats non sélectionnés et contrôle des empreintes ;
`OfficialGitLab` porte HTTP, endpoints officiels et parsing, `TomlRemoteSettings`
porte TOML. Aucun appel distant n’entre dans LocalResolver ou les services M0–M8.

L’activation est explicite et locale ; construire l’adaptateur n’ouvre aucune
connexion. Une recherche résout la révision en commit puis utilise ce commit
pour tous ses octets. La copie distante n’a lieu qu’au clic de téléchargement :
nouvel Asset UNCHECKED dans le store, sans modification d’une installation KiCad,
association ou remplacement de choix. Après cette matérialisation explicite, les
services M4–M8 restent autonomes. L’URL avec commit/révision et le hash identifient
la provenance. Les symboles multi-entrées utilisent le sélecteur M8 existant.

Les ressources importées de cette source viennent après les trois tiers locaux.
Une recherche locale reste indépendante de la configuration et des erreurs M9.
Qt exécute les lectures distantes en worker, puis la sauvegarde locale sur le
thread UI. Pas de nouvelle dépendance, migration ni format de publication.
Voir [REMOTE_KICAD.md](REMOTE_KICAD.md) pour périmètre, erreurs et compatibilité.


## Documentation et identification M10

`domain/documentation.py` décrit un profil par Part, des propositions de champs
et un historique des acceptations avant/après avec source déclarée et horodatage.
Le profil est séparé de Part : aucun changement du nom, de la description ou de
l’identité métier. Une valeur déjà renseignée et différente est un conflit,
y compris un effacement ; son remplacement demande une confirmation explicite.

`application/documentation.py` orchestre acceptation, fiches descriptives PDF,
import, restitution et téléchargement optionnel via `ports/documentation.py`.
Les fiches associent un Part à un Asset DATASHEET existant ou nouveau ; elles
ne changent pas les ResourceChoice et ne confèrent aucune qualification M5.
La provenance d’un PDF existant n’est pas réécrite par sa fiche descriptive.

`SqliteDocumentation` conserve profil/historique JSON et fiches JSON dans deux
tables ajoutées par `0006_documentation`. Le profil est écrit avec contrôle
optimiste de la révision et du snapshot attendu sous BEGIN IMMEDIATE. L’ajout
d’une fiche, de son association et éventuellement de l’asset est atomique.
Un couple Part/Asset ne peut avoir qu’une fiche immuable. Les octets restent
dans l’Asset Store M2 ; un blob orphelin après rollback est permis, pas une
association incomplète. Un downgrade refuse de supprimer des données M10.

`LocalProposalReader` lit un JSON local borné ; aucune lecture de proposition
n’enregistre de valeurs. `ManufacturerSettings` persiste les autorisations
locales en TOML atomique. `domain/datasheets.py` contrôle opt-in, domaines DNS
exacts, URL HTTPS et résultat PDF borné. `ManufacturerPDFs` est l’unique adaptateur
HTTP : requête explicite seulement, redirections refusées et limites de lecture.
L’application recontrôle l’autorisation et la correspondance de provenance avant
import. La composition instancie l’adaptateur sans requête au démarrage.

Le nouvel onglet Documentation de Composants emploie les primitives partagées,
une étape de comparaison distincte et un formulaire d’ajout à affichage progressif.
Le worker ne touche pas SQLite ; l’enregistrement passe par le thread UI après
réception des octets. La fermeture attend sa fin. Fournisseur absent, panne et
configuration incorrecte ne changent pas le cœur local.

Aucune nouvelle dépendance ; aucun serveur, IA ou génération. Le format M8 v1
et les manifests M7 sont inchangés. Les PDF choisis restent publiables et
transportables sous les règles existantes ; les profils/historiques et fiches
M10 ne sont pas des dépendances du build et restent locaux. Voir
[DOCUMENTATION.md](DOCUMENTATION.md) pour les limites et le parcours utilisateur.


## M10.5 — Frontière tiers et provenance

`domain/third_party_assets.py` représente requête exacte, candidat distant et contenu
borné ; `domain/asset_provenance.py` représente provenance et droits déclarés. Aucun
module domaine ne dépend de SnapMagic, HTTP, Qt, SQLAlchemy ou du système de fichiers.
`ports/third_party_assets.py` sépare fournisseur, configuration et inspection.
`application/third_party_assets.py` exige l’activation, vérifie la correspondance,
réutilise l’Asset Store puis crée un asset distinct sans ResourceChoice ni qualification.

`infrastructure/snapmagic.py` prépare un adaptateur autour d’un contrat **interne**
normalisé. Aucun client HTTP réel n’est composé sans documentation partenaire.
Inspection temporaire et ZIP borné précèdent l’import ; les erreurs confidentielles
ne remontent pas dans l’UI. Le secret est lu en mémoire, jamais persisté.
La migration `0007_asset_provenance` ajoute une colonne nullable, conserve les assets
antérieurs et refuse un downgrade destructeur. Les migrations SQLite emploient une
transaction explicite pour assurer le rollback du DDL et de la version ensemble.

La provenance attachée à un asset est immuable. Le resolver local classe les tiers
après les sources constructeur et officielles, sans faire d’appel tiers implicite.
`ThirdPartyPanel` s’intègre dans `ResolverDialog` ; le worker n’utilise pas SQLite.
M8 v1 reste inchangé et ne transporte pas les champs détaillés de licence ; le
réimport compatible conserve ceux déjà présents localement. Voir
[SNAPMAGIC.md](SNAPMAGIC.md) et [ADR 0001](adr/0001-third-party-assets.md).


## M11 — Assistance d’identification facultative

`domain/assistance.py` décrit configuration bornée et contexte explicitement partagé.
Le domaine ne dépend d’aucun fournisseur. `ports/assistance.py` sépare configuration
et fournisseur ; `application/assistance.py` exige consentement et activation,
recontrôle la configuration et retourne une proposition, sans accès au catalogue.

`infrastructure/assistance.py` fournit Gemini natif, Chat Completions et Ollama
loopback via la bibliothèque standard ; POST explicite, JSON borné, refus des
redirections et erreurs normalisées. Les clés restent en environnement. Aucun SDK,
serveur, téléchargement de modèle ou dépendance ajoutée.

`ui/assistance_panel.py` s’insère dans Documentation. Le contexte est préparé et
relu avant autorisation ; le worker ne touche pas SQLite. L’UI écarte une réponse
si l’identification a changé, puis ouvre la comparaison M10, champs tous décochés.
`MetadataSource` accepte désormais GENERATED_AI pour l’historique JSON existant ;
aucune migration nécessaire. L’acceptation M10 conserve origine IA, endpoint/modèle
et hash/date du contexte, avant/après et contrôle optimiste. L’IA ne peut modifier
Part, ResourceChoice, asset, qualification ou publication. Les propositions refusées
restent sans effet ; contexte complet et réponse brute non persistés. Voir
[ASSISTANCE.md](ASSISTANCE.md) pour les contrats, la configuration et les limites live.

## Inspection locale UX A1

Le service applicatif `Previews` utilise le port en lecture seule `PreviewReader`.
Les DTO `PreviewContent`, `Drawing` et `Primitive` ne dépendent pas de Qt.
`LocalPreviewReader` contrôle les snapshots par SHA-256 et protège les racines ;
`kicad_preview.py` interprète la géométrie. `PreviewDialog` rend les primitives
avec Qt Graphics View et les PDF avec QtPdf, sans accès direct aux fichiers.
La composition est optionnelle pour les tests et compositions partielles.
L’inspection ne change aucune association, sélection ou qualification M5.
Aucune migration ni dépendance CAO n’est ajoutée. Détails dans
[ASSET_PREVIEWS.md](ASSET_PREVIEWS.md).

## Inspection 3D UX A2

`PreviewContent` peut désormais contenir un `Mesh` neutre (sommets, faces convexes,
matériaux diffus, limites signalées), réexporté par l’application pour l’UI.
`LocalPreviewReader` conserve le même chemin de snapshots vérifiés avant de déléguer
au module d’infrastructure `model_preview.py` : parseur VRML97 borné ou adaptateur
STEP FreeCAD local facultatif. Aucun import du noyau CAO dans le processus principal,
aucun appel réseau ni nouveau service applicatif générique. Les maillages et les
snapshots de conversion sont éphémères et distincts des assets électroniques gérés.

L’UI `ModelView` reçoit seulement le maillage ; projection et tampon de profondeur
logiciels sont locaux à la présentation. `PreviewDialog` réutilise provenance,
contrôles, thème et mode non modal d’A1, avec un worker réservé à la lecture 3D et
une protection de sa durée de vie jusque dans MainWindow et ResolverDialog.
FreeCAD n’est découvert/lancé qu’à la demande ; son absence ne bloque pas le cœur.
Ni migration, ni générateur, ni nouvelle dépendance Python. Couverture et limites :
[ASSET_PREVIEWS.md](ASSET_PREVIEWS.md).

## Prototype FabParts TECH-01 / TECH-01B

Le prototype isolé `prototypes/fabparts-tech-01` utilise Svelte/Tauri et le point
headless `kipartmanager.headless`, sans remplacer le bootstrap PySide6. Python
reste seul responsable des lectures métier ; Rust possède uniquement le sidecar
et l’IPC privé JSONL v1. La WebView n’a aucune permission SQL/filesystem/shell.
Seule une copie explicitement choisie, figée et compatible est ouverte en lecture
seule ; aucune migration, indexation ni initialisation de l’Asset Store.
Voir [ADR 0002](adr/0002-headless-readonly-sidecar.md). Aucun workflow d’écriture supplémentaire
n’est autorisé par ce prototype.

## Aperçus du frontend Tauri TECH-02A

Le sidecar compose `AssetPreviews` et `ReadonlyPreviews` autour du port `PreviewReader`
et du service `Previews` historiques. Les primitives KiCad traversent JSONL v1 et
s’affichent en SVG Svelte. Les PDF utilisent des snapshots mémoire à handles bornés,
un transfert par blocs et PDF.js local dans un worker. Qt reste absent du processus
headless. Les frontières et limites sont décrites dans
[l’extension de l’ADR 0002](adr/0002-headless-readonly-sidecar.md#extension-tech-02a--25-octobre-2026).

## TECH-04A — Espace personnel

Le host Tauri ouvre normalement le workspace système FabParts via `--personal`.
Les chemins writable restent définis côté host. Le mode explicite readonly et le
sandbox TECH-03 conservent leurs frontières. `headless.py` compose les services
existants et injecte l'initialisation Catalogue à `user_workspace.py`, sans
introduire de dépendance Infrastructure → Application.

`user_workspace.py` gère le verrou, le marqueur, le pointeur de génération et les
migrations contrôlées. `workspace_backup.py` fournit l'unique implémentation de
snapshot complet et de vérification, réutilisée par le sandbox. Rust acquiert la
source de restauration par sélecteur natif et limite les capacités à la session.
Voir [ADR 0004](adr/0004-personal-workspace-and-verified-backups.md).
