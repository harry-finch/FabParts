# KiPart Manager — Spécification produit

## Statut et mission

Document de référence produit, établi avant M0. M0 à M10 sont livrées : catalogue,
stocks, métadonnées, fichiers d’assets, index KiCad et sélections de ressources
sont gérés localement. La validation locale et la construction KiCad sont
disponibles ; M7/M8 livrent les publications immuables et leur transfert portable.
M9 livre une recherche officielle distante facultative ; M10 ajoute les profils
d’identification traçables, les fiches PDF et leur téléchargement constructeur
explicitement autorisé. M10.5 prépare une source SnapMagic optionnelle avec
provenance et droits déclarés ; sa connexion API attend le contrat partenaire.
M11 livre une assistance d’identification optionnelle (Gemini/Ollama/API compatible),
avec contexte explicite et acceptation par champ. M12+ restent des objectifs. Le plan de livraison et
les critères vérifiables figurent dans [MILESTONES.md](MILESTONES.md) ; les
responsabilités techniques dans [ARCHITECTURE.md](ARCHITECTURE.md).

KiPart Manager est une application desktop de gestion de composants électroniques,
principalement destinée à KiCad. Elle permet progressivement d'identifier les
composants, d'associer symboles, footprints, modèles 3D et datasheets, de gérer
leurs fichiers, de vérifier leur cohérence et de publier des collections portables.

## Invariants produit

1. Le cœur fonctionne sans Internet, serveur ni fournisseur d'IA, y compris le
   catalogue, les stocks, les assets, l'indexation locale, la résolution locale,
   la validation, la publication et le transfert portable.
2. La base SQLite locale et l'Asset Store géré sont les sources de vérité du
   catalogue courant. Les manifests immuables décrivent les états publiés.
   Les bibliothèques KiCad produites sont des artefacts reconstruisibles.
3. Un asset utilisateur n'est jamais remplacé silencieusement. Plusieurs candidats
   peuvent coexister ; le choix ou le remplacement doit être explicite.
4. Les bibliothèques officielles KiCad sont consultées en lecture seule.
5. Provenance, empreinte SHA-256 et état de validation sont conservés pour les
   ressources gérées ; les dépendances externes publiées sont identifiables.
6. Une ERROR bloque la publication. Tout asset généré exige une validation
   explicite avant publication ; la génération est hors MVP.
7. Une publication versionnée est immuable. Une modification crée une nouvelle
   version, jamais une réécriture de la précédente.
8. Les artefacts portables ne contiennent pas de dépendance à un chemin absolu
   propre à la machine d'origine.

## Vocabulaire et relations

Les entités persistantes utilisent des UUID comme identifiants stables.

| Notion | Rôle |
| --- | --- |
| Part | Référence de composant du catalogue : STM32F103C8T6, ADS1115IDGSR, NE555P ou module. Les composants génériques sont une extension future. |
| Package | Entité mécanique partageable entre Parts ; peut être associée à plusieurs footprints et modèles 3D. |
| Asset | Ressource typée et traçable : SYMBOL, FOOTPRINT, MODEL_3D ou DATASHEET. |
| Inventory | Ensemble de stocks indépendant du catalogue ; inventaires initiaux Lab et Personal. |
| StockItem | Association d'une Part à un inventaire, avec quantité et localisation éventuelle ; granularité précise à décider en M1. |
| Location | Emplacement de stockage physique ; organisation à préciser en M1. |
| Collection | Sélection de Parts à exposer à KiCad ; collections initiales LabParts et PersonalParts. |
| Publication | État reproductible d'une collection ; versions immuables et manifests introduits en M7. |

Relations conceptuelles : une Part référence un symbole, une ou plusieurs
datasheets et un Package ; le Package référence des footprints et modèles 3D ;
un footprint peut référencer des modèles 3D. Les cardinalités exactes seront
fixées dans les milestones concernées. Les ressources mécaniques sont partagées,
sans copies indépendantes imposées pour chaque Part.

Une Part reste connue et publiable avec un stock nul. Inventory et Collection
sont indépendants : publier ne dépend pas de la possession physique du composant.

## Assets et provenance

Origines prévues : USER_PROVIDED, KICAD_OFFICIAL, MANAGED_LIBRARY, MANUFACTURER,
TRUSTED_THIRD_PARTY, GENERATED_PARAMETRIC et GENERATED_AI. Cette liste décrit le
vocabulaire cible ; elle n'autorise pas l'implémentation anticipée des adaptateurs.

Formats d'import M2 : PDF, STEP, WRL, `.kicad_mod`, `.kicad_sym`. L'import et le
stockage d'un fichier n'impliquent pas sa validité sémantique ; M5 apporte les
premiers contrôles de cohérence. La déduplication de contenu ne doit pas effacer
les provenances ou associations distinctes.

M2 stocke les fichiers non vides des extensions prises en charge, avec SHA-256,
taille, extension et nom original. STEP accepte aussi `.stp`. Les octets sont
dédupliqués, les assets/provenances restent distincts. Une fiche peut rester sans
fichier ou recevoir un premier fichier ; une association existante est immuable.
L'intégrité est vérifiable indépendamment de l'état sémantique UNCHECKED.

Une référence officielle KiCad désigne une ressource externe installée localement.
Un managed asset désigne un fichier canonique de l'Asset Store. Une copie d'une
ressource officielle conserve son origine et devient un fichier géré distinct.

## Résolution KiCad-first

Ordre conceptuel de recherche :

1. Ressource fournie par l'utilisateur.
2. Catalogue géré.
3. Bibliothèque officielle KiCad installée localement.
4. Bibliothèque officielle KiCad distante, optionnelle à partir de M9.
5. Constructeur.
6. Source tierce explicitement autorisée.
7. Génération en dernier recours, hors MVP.

La priorité guide la recherche, sans remplacer une sélection utilisateur.
Les candidats utilisateur et officiels peuvent être proposés séparément et comparés.
Le resolver MVP se limite aux trois premières sources et ne génère aucun asset.

## Cycle de vie et validation

Cycle envisagé : DRAFT → IDENTIFIED → RESOLVING → READY_FOR_REVIEW → VALIDATED
→ PUBLISHED → DEPRECATED. Les transitions et préconditions appartiennent au
domaine ; ce schéma exprime une intention, pas une obligation d'implémenter
dès M1 toutes les opérations des milestones suivantes.

Les contrôles M5 produisent PASS, WARNING ou ERROR sur un rapport de Part ou
Collection. ERROR bloque la qualification ; WARNING exige une acceptation explicite
d'un rapport actuel. Les modifications pertinentes rendent le rapport STALE,
y compris les changements de fichiers. Le statut global des assets reste UNCHECKED :
les contrôles ne constituent pas une certification CAO exhaustive. Voir
[VALIDATION.md](VALIDATION.md) pour couverture, préconditions et invalidation. Le statut PUBLISHED d'une Part ne
remplace pas l'historique des publications par collection.

## Livraison

M0 à M8 constituent le parcours MVP : bootstrap, domaine/persistance, Asset Store,
index KiCad local, resolver local, validation, publisher, versions immuables,
puis export/import `.kiparts` (ZIP + manifest JSON). **M8 termine le MVP.**

M9 à M17+ sont hors MVP : recherche distante, métadonnées/datasheets enrichies,
assistance IA, générations, distribution, mises à jour des postes et extensions.
L'import PDF de M2 reste distinct des fonctions enrichies de M10.

L'IA future suit : source → représentation structurée validable → validation
→ générateur déterministe → asset KiCad. Exemples : PinSpec pour un symbole,
PackageSpec pour un footprint. Du texte brut de LLM ne devient jamais directement
un asset lorsqu'une représentation structurée et un générateur peuvent être utilisés.

## Décisions à confirmer ultérieurement

- M1 a fixé les cardinalités initiales et le stock entier par composant/inventaire ;
  voir les décisions M1 de l'architecture. Les stocks multi-emplacements,
  les liens footprint/3D et les transitions de résolution/publication restent futurs.
- M3 livrée : versions, découverte et références décrites dans [KICAD_INDEX.md](KICAD_INDEX.md).
- M5 : règles et limites définies dans [VALIDATION.md](VALIDATION.md) ; extensions
  de couverture à cadrer séparément.
- M6–M7 livrées : copie autonome et versions historiques avec dépendances retenues ;
  voir [PUBLISHER.md](PUBLISHER.md) et [PUBLICATIONS.md](PUBLICATIONS.md).
- M8 : collisions d'import et transport/compatibilité des bundles restent à cadrer.
- M9+ : sources distantes autorisées, conditions de redistribution, fournisseurs
  optionnels et mécanismes de distribution. Aucun de ces choix n'est acquis.


## Source tierce optionnelle M10.5

Recherche explicite par MPN exact après les sources utilisateur, gérées, officielles
et constructeur. Les candidats distants restent distincts des assets importés ;
un import ne remplace aucun choix et ne confère aucune qualification. Fournisseur
absent, désactivé, non configuré ou indisponible : cœur local conservé.
Provenance durable et état de redistribution `unknown` par défaut ; une licence
communiquée ne vaut pas autorisation générale d’export. Aucun secret métier persisté.
Le format M8 v1 reste inchangé ; les nouveaux droits détaillés restent locaux.
La connexion réelle exige un contrat API partenaire vérifié. Voir [SNAPMAGIC.md](SNAPMAGIC.md).
