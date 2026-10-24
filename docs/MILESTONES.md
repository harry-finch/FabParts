# KiPart Manager — Plan de livraison

Les jalons ci-dessous décrivent le moteur Python historique et les objectifs ultérieurs.
Les comptes rendus internes antérieurs au snapshot public ne sont pas distribués.
Le statut du prototype Tauri et les limites actuelles figurent dans le README.

## Discipline et état actuel

Le moteur historique couvre les jalons M0 à M11 et les aperçus UX A1/A2. M8
marque la fin du MVP historique. M10.5 fournit un adaptateur testé avec un
fournisseur simulé ; la connexion API partenaire reste en attente. Les jalons
M12 à M17+ et les phases UX B–E ne sont pas démarrés. Une milestone à la fois,
sans anticiper les fonctionnalités suivantes. Ce statut ne décrit pas les
fonctionnalités connectées dans le prototype Tauri ; voir le README.

Les invariants de [PROJECT_SPEC.md](PROJECT_SPEC.md) et les frontières de
[ARCHITECTURE.md](ARCHITECTURE.md) s'appliquent à chaque étape. Les critères
hors MVP constituent une base de cadrage à préciser au lancement de chaque
milestone, sans affaiblir les invariants.

## Checkpoint commun obligatoire

Le checkpoint de chaque milestone comprend :

1. Comparer le résultat à tous ses critères d'acceptation ; signaler tout critère
   non vérifié et ne pas déclarer la milestone terminée s'il reste insatisfait.
2. Inspecter le diff final et vérifier le périmètre et les frontières architecturales.
3. Exécuter toute la suite de tests actuellement configurée et les contrôles
   qualité pertinents ; distinguer les échecs nouveaux des échecs préexistants.
4. Exécuter les vérifications spécifiques indiquées ci-dessous ; consigner les
   limites de l'environnement et les validations manuelles restantes.
5. Rapporter fonctionnalités, résultats des tests, décisions architecturales,
   limites connues et fichiers ajoutés/modifiés ; mettre à jour la documentation.
6. **S'arrêter sans commencer la milestone suivante.**

Les checkpoints spécifiques ci-dessous s'ajoutent tous à ce checkpoint commun.
Utiliser les skills locales selon le travail : vérification Python, migrations,
workflow KiCad, garanties hors ligne et checkpoint ; ne pas les appliquer hors sujet.

## M0 — Bootstrap et architecture

- **Objectif :** obtenir une base Python desktop minimale et vérifiable.
- **Périmètre :** initialisation Git si nécessaire, packaging Python 3.12+,
  arborescence des couches, démarrage PySide6 minimal, tests et outils de qualité
  légers configurés, instructions de développement.
- **Hors périmètre :** entités persistantes, base métier, Asset Store, index KiCad,
  génération, réseau et IA.
- **Acceptation :** installation et lancement documentés et vérifiés ; fenêtre
  minimale ouvrable ; tests et contrôles configurés passent ; domaine indépendant
  des adaptateurs ; démarrage sans réseau ; aucune fonction de M1+ introduite.
- **Checkpoint :** vérifier installation, lancement/fermeture et commandes de qualité
  dans l'environnement disponible ; rapporter les limites de vérification GUI.

## M1 — Modèle de domaine et persistance

- **Objectif :** gérer un catalogue et des stocks locaux persistants.
- **Périmètre :** Part, Package, Asset (métadonnées), Inventory, StockItem, Location,
  Collection ; UUID ; règles initiales de domaine ; SQLite/SQLAlchemy 2/Alembic ;
  UI minimale de manipulation ; inventaires Lab/Personal et collections LabParts/PersonalParts.
- **Hors périmètre :** import de fichiers M2, indexation, résolution, validation
  KiCad, publication et transitions qui exigent ces fonctions futures.
- **Acceptation :** création, consultation et modification persistées après
  redémarrage ; Package partageable ; stock indépendant du catalogue et des
  collections ; Part conservée à quantité nulle ; initialisation répétable sans
  doublons des ensembles initiaux ; migrations et contraintes vérifiées ; ORM
  séparé du domaine ; cardinalités et règles de stock documentées.
- **Checkpoint :** base neuve créée par migrations, parcours UI minimal et tests
  métier/persistance ; vérifier les migrations depuis une révision précédente si applicable.

## M2 — Asset Store

- **Objectif :** conserver et retrouver les fichiers gérés avec intégrité et provenance.
- **Périmètre :** import PDF, STEP, WRL, `.kicad_mod`, `.kicad_sym` ; stockage
  canonique, SHA-256, déduplication et associations aux métadonnées M1.
- **Hors périmètre :** index officiel, resolver, validation sémantique complète,
  publication et génération.
- **Acceptation :** chaque format prévu dispose d'un import et d'une restitution
  testés ; hashes corrects ; contenu identique dédupliqué sans perte de provenance ;
  fichiers sources non modifiés ; aucun remplacement silencieux ; erreurs de
  lecture/écriture signalées sans association valide vers un fichier absent ;
  comportement après interruption et détection d'intégrité documentés et testés.
- **Checkpoint :** importer les cinq formats sur données jetables, tester doublons
  et erreurs d'accès, vérifier octets/hashes et cohérence base/store.

## M3 — Index KiCad local

- **Objectif :** rechercher les ressources officielles installées sans réseau.
- **Périmètre :** découverte/configuration des installations, index local
  reconstruisible des symboles, footprints et modèles 3D, références stables.
- **Hors périmètre :** copie systématique vers le store, réseau, resolver de Part,
  publication et génération.
- **Acceptation :** versions supportées documentées ; découverte ou configuration
  manuelle possible ; recherche sur fixtures représentatives ; reconstruction
  reproductible de l'index ; absence d'installation et formats non supportés
  explicitement traités ; fichiers officiels inchangés ; références distinctes
  des fichiers gérés ; aucune requête réseau nécessaire.
- **Checkpoint :** reconstruire l'index, comparer les résultats et vérifier la
  lecture seule ; essai sur une installation réelle si disponible.

## M4 — Resolver local

- **Objectif :** proposer des candidats locaux pour les ressources d'une Part.
- **Périmètre :** user provided → managed catalogue → local KiCad ; candidats
  distincts, provenance, choix explicite et associations via l'application/UI.
- **Hors périmètre :** réseau, génération, validation complète et publication.
- **Acceptation :** priorité locale testée ; coexistence utilisateur/officiel
  visible ; ressource utilisateur jamais remplacée silencieusement ; sélection
  persistée ; absence de candidat clairement présentée ; fonctionnement sans
  installation KiCad et sans réseau pour les sources disponibles.
- **Checkpoint :** résoudre des cas utilisateur, géré, officiel, concurrents et
  sans résultat ; vérifier le maintien des sélections existantes.

## M5 — Validation locale

- **Objectif :** qualifier la cohérence des associations avant publication.
- **Périmètre :** premiers contrôles symboles/footprints/packages/modèles 3D,
  rapports PASS/WARNING/ERROR, état de validation et règles métier associées.
- **Hors périmètre :** publisher, génération, validation CAO exhaustive et services distants.
- **Acceptation :** règles et couverture documentées ; cas valides, avertissements,
  erreurs et entrées malformées testés ; résultats traçables aux assets contrôlés ;
  ERROR rend la collection non publiable selon les contrôles obligatoires ;
  politique WARNING explicite ; modification pertinente invalide une validation
  devenue obsolète ; aucune validation automatique infondée des formats non couverts.
- **Checkpoint :** exécuter les fixtures de cohérence et vérifier le blocage métier
  des erreurs ainsi que l'invalidation ; consigner les limites des contrôles.

## M6 — Publisher KiCad

- **Objectif :** construire des bibliothèques exploitables par KiCad.
- **Périmètre :** construction de LabParts/PersonalParts depuis les collections,
  symboles, footprints et liens 3D nécessaires ; modes de références/copies
  explicités ; chemins portables dans les artefacts destinés au transfert.
- **Hors périmètre :** gestion des versions immuables/manifests M7, `.kiparts`,
  génération de nouveaux assets et modification des bibliothèques officielles.
- **Acceptation :** collections produites séparément ; sorties compatibles avec
  les versions KiCad supportées ; associations et liens résolus ; ERROR bloque
  la construction publiable ; sorties reconstruisibles selon le mode documenté ;
  ressources utilisateur et officielles préservées ; dépendances externes explicites.
- **Checkpoint :** construire les deux collections, contrôler formats et chemins,
  vérifier l'ouverture dans KiCad et un cas bloqué par ERROR.

## M6-UI — Refonte UI/UX et socle visuel

- **Objectif :** une interface desktop claire et cohérente pour les workflows M0–M6.
- **Périmètre :** sidebar, headers, listes/détails, recherche, formulaires, états,
  thème clair centralisé et composants légers réutilisables.
- **Hors périmètre :** changements métier, M7+, réseau, IA, génération et versions.
- **Acceptation :** navigation cohérente ; langage graphique partagé ; apparence
  soignée ; workflows M1–M6 préservés ; listes/formulaires lisibles ; états textuels
  cohérents ; états vides utiles ; redimensionnement utilisable ; styles centralisés ;
  composants réutilisables ; tests existants passants ; aucune fonctionnalité M7+.
- **Checkpoint :** lancer l'application native, inspecter toutes les pages et
  formulaires, états vides/remplis/sélectionnés et erreurs/warnings, à environ
  1200×800, plus étroit et plus large ; corriger les défauts visibles ; documenter
  les conventions effectives dans [UI_GUIDELINES.md](UI_GUIDELINES.md).

## M7 — Publications versionnées

- **Objectif :** figer des états de collection reproductibles et immuables.
- **Périmètre :** version, manifest, hashes, instantané des associations,
  conservation des dépendances nécessaires et engagement cohérent des publications.
- **Hors périmètre :** transport `.kiparts`, serveur, synchronisation et génération.
- **Acceptation :** publication existante jamais écrasée ; édition du catalogue
  sans effet sur les anciennes versions ; manifest identifiant assets et
  dépendances par hashes ; version reconstruisible selon une garantie documentée
  et testée ; stratégie pour les ressources officielles modifiées/disparues ;
  échec de publication sans version partielle présentée comme valide.
- **Checkpoint :** publier deux versions, vérifier l'immuabilité de la première,
  l'intégrité et une reconstruction après changement des données courantes.

## M8 — Export/import `.kiparts` — Fin du MVP

- **Objectif :** transférer une bibliothèque complète vers une autre machine.
- **Périmètre :** ZIP + manifest JSON, publication et dépendances portables,
  vérification d'intégrité, import vers base/store locaux, politique de conflits.
- **Hors périmètre :** distribution serveur, synchronisation, recherche distante et IA.
- **Acceptation :** aller-retour sur deux dossiers de données indépendants ;
  bibliothèque importée utilisable sans chemins absolus ni fichiers de la machine
  source ; hashes/provenance/version conservés ; conflits UUID/contenu traités
  explicitement sans remplacement silencieux ; archives altérées, formats non
  supportés et chemins sortant de la destination rejetés ; échecs sans import
  partiel présenté comme réussi ; aucun réseau requis.
- **Checkpoint :** exporter puis importer dans un environnement vierge, vérifier
  les liens KiCad, les conflits et les archives invalides ; rapport final du MVP,
  puis arrêt avant M9.

## M9 — Recherche officielle KiCad distante optionnelle

- **Objectif :** compléter les candidats locaux par une source officielle distante.
- **Périmètre :** adaptateur officiel GitLab optionnel, activation explicite TOML,
  recherche dans une bibliothèque précise à une révision fixée, candidats distincts,
  téléchargement explicite comme nouvel asset géré UNCHECKED, provenance et erreurs réseau.
  Voir [REMOTE_KICAD.md](REMOTE_KICAD.md) pour ce cadrage et ses limites.
- **Hors périmètre :** dépendance réseau du cœur, IA et génération.
- **Acceptation :** source officielle et versions identifiables ; candidats
  distincts ; priorité locale préservée ; panne ou absence d'adaptateur sans
  blocage du cœur ; ressource utilisateur préservée.
- **Checkpoint :** vérifier adaptateur disponible, désactivé et en échec ; rejouer
  les parcours locaux avec réseau indisponible.

## M10 — Métadonnées et datasheets

- **Objectif :** enrichir l'identification et la documentation des Parts.
- **Périmètre :** métadonnées et gestion enrichie des datasheets ; sources
  constructeur et éventuelles sources tierces explicitement autorisées, à cadrer.
  **Périmètre livré :** profils locaux et propositions JSON relues, fiches PDF
  additives, téléchargement HTTPS de PDF depuis des domaines constructeurs
  autorisés explicitement ; désactivé par défaut, aucun domaine préautorisé.
  Sources tierces seulement déclarées dans les propositions locales.
- **Hors périmètre :** simple import PDF déjà livré en M2, IA et génération.
- **Acceptation :** enrichissements traçables ; conflits avec saisie utilisateur
  explicites ; fichiers PDF existants préservés ; gestion locale possible ; toute
  récupération distante optionnelle et tolérante aux pannes.
- **Checkpoint :** vérifier enrichissement, conflits, provenance et fonctionnement hors ligne.

## M10.5 — SnapMagic / SnapEDA Asset Resolver

- **Objectif :** proposer une source tierce optionnelle pour les ressources manquantes.
- **Périmètre :** MPN exact, constructeur facultatif, inspection des candidats,
  import explicite géré, provenance durable et droits de redistribution déclarés.
- **Priorité :** utilisateur → géré → KiCad local → officiel distant → constructeur → tiers.
- **Accès réel :** vérifier contrat/authentification/endpoints/quotas/droits avant
  tout client HTTP. Si indisponible, livrer port/adaptateur et tests avec faux
  fournisseur, documenter les opérations réelles non vérifiées sans bloquer le reste.
- **Hors périmètre :** IA, génération, scraping, téléchargement massif, refonte M8.
- **Acceptation :** resolver facultatif ; recherche par MPN ; candidats inspectables ;
  import choisi dans l’Asset Store ; indépendance des fichiers temporaires ; hash et
  provenance durables ; qualification normale ; priorités inchangées ; fournisseur,
  credentials ou réseau absents tolérés ; droits sans autorisation inventée ; tests
  anciens/nouveaux passants ; aucune IA M11.
- **Checkpoint :** distinguer fixtures et accès partenaire réel, rapporter UI,
  configuration, import, provenance, droits, vérifications et limites, puis arrêter.

## M11 — IA d'assistance optionnelle

- **Objectif :** assister l'utilisateur sans transférer l'autorité à l'IA.
- **Périmètre :** suggestions structurées d’identification, fournisseur optionnel,
  révision humaine via comparaison/historique M10. Fournisseurs retenus : Gemini
  natif, Ollama local et API compatible OpenAI ; contexte textuel choisi et relu,
  champs d’identification inclus uniquement sur demande, consentement par requête.
- **Hors périmètre :** génération de fichiers KiCad, remplacement autonome des données.
- **Acceptation :** propositions séparées des données acceptées ; validation
  explicite des changements ; fournisseur absent ou en erreur sans effet sur le
  cœur ; données envoyées et configuration explicites ; provenance conservée.
- **Checkpoint :** tester acceptation/rejet, réponses invalides et fournisseur indisponible.

## M12 — Génération de symboles

- **Objectif :** générer un symbole lorsque la recherche préalable n'a pas fourni de solution retenue.
- **Périmètre :** source → PinSpec validable → validation → générateur déterministe
  → symbole ; provenance et validation explicite avant publication.
- **Hors périmètre :** génération de footprints/3D, écriture brute de texte LLM en asset.
- **Acceptation :** recherche préalable incluant KiCad local ; PinSpec valide et
  rejet des entrées invalides ; génération déterministe ; format KiCad testé ;
  asset marqué généré ; publication impossible sans validation explicite.
- **Checkpoint :** vérifier les cas de recherche, génération, invalidité et publication bloquée.

## M13 — Génération de footprints

- **Objectif :** générer un footprint depuis une description de package validée.
- **Périmètre :** recherche préalable, PackageSpec, contrôles dimensionnels,
  générateur déterministe et validation explicite.
- **Hors périmètre :** génération 3D et sortie KiCad arbitraire d'un LLM.
- **Acceptation :** ressources existantes considérées ; unités, dimensions et
  associations cohérentes ; entrées invalides rejetées ; sortie déterministe et
  compatible KiCad ; provenance et blocage avant validation conservés.
- **Checkpoint :** contrôler des packages représentatifs et cas invalides ;
  vérifier les sorties et le parcours de validation.

## M14 — Gestion avancée / génération paramétrique de modèles 3D

- **Objectif :** enrichir les modèles mécaniques selon un besoin explicitement cadré.
- **Périmètre :** gestion avancée et/ou génération paramétrique structurée,
  recherche préalable, cohérence avec packages/footprints et validation.
- **Hors périmètre :** ajout anticipé d'un moteur CAO lourd, serveur et synchronisation.
- **Acceptation :** formats, unités et transformations documentés ; sources
  existantes recherchées ; génération reproductible lorsqu'incluse ; cohérence
  mécanique vérifiée ; provenance et validation explicite des assets générés.
- **Checkpoint :** vérifier les cas mécaniques retenus ; justifier toute dépendance CAO ajoutée.

## M15 — Serveur facultatif de distribution

- **Objectif :** distribuer des publications sans déplacer la source de vérité locale.
- **Périmètre :** protocole et serveur optionnel de distribution de versions immuables.
- **Hors périmètre :** serveur indispensable, synchronisation bidirectionnelle
  du catalogue et mise à jour automatique des postes M16.
- **Acceptation :** versions et hashes conservés ; transfert vérifié ; erreurs
  explicites ; cœur opérationnel serveur absent ; politique d'accès définie au cadrage.
- **Checkpoint :** tester distribution, intégrité, accès et indisponibilité du serveur.

## M16 — Mise à jour automatique des postes publics

- **Objectif :** installer automatiquement des publications selon une politique explicite.
- **Périmètre :** détection, transfert, validation et activation de versions sur
  les postes publics ; récupération après échec.
- **Hors périmètre :** écrasement du catalogue utilisateur et dépendance permanente au serveur.
- **Acceptation :** versions vérifiées avant activation ; échec laissant la
  dernière version valide utilisable ; fonctionnement hors ligne ; politique de
  mise à jour et retour arrière documentée ; aucun asset utilisateur remplacé silencieusement.
- **Checkpoint :** tester mise à jour, interruption, corruption et maintien de la version valide.

## M17+ — Extensions à cadrer séparément

- **Objectif :** répondre à des besoins avancés après les livraisons précédentes.
- **Périmètre :** pistes BOM, équivalents, code-barres, vision, stocks avancés,
  imports distributeurs, bundles de projet ; chaque piste devient une milestone distincte.
- **Hors périmètre :** implémentation globale implicite de cette liste ou remise
  en cause des invariants local-first.
- **Acceptation :** pour chaque extension choisie, objectif, périmètre, exclusions,
  critères mesurables et risques définis avant développement ; validations et
  tests passent ; adaptateurs externes optionnels et provenance préservée.
- **Checkpoint :** appliquer le checkpoint commun à chaque extension cadrée,
  rapporter ses critères propres puis s'arrêter.
