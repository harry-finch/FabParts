# FabParts 2.0 — TECH-05A : publications KiCad versionnées

Date : 26 octobre 2026. Branche : `tech/05a-versioned-publications`.

## Base et services réutilisés

PR TECH-04B #5 vérifiée ouverte, prête, sans conflit, head `f41d68d`.
GitHub n’exposait ni statuts ni workflows pour ce commit. Fusion par **Create a
merge commit** : `e65c8c41253fea75f7db44fce6bcccc12726dc7f`, parents `0065a8e`
et `f41d68d`. Checkout propre avancé sur `origin/main` avant création de la branche.
Aucune protection contournée ; origin reste `harry-finch/FabParts`.

La composition headless utilise **LocalPublisher, LocalLibraryBuilder, Publications
et LocalPublications**, avec LocalValidation M5. PublicationReview est un adaptateur
de présentation, sans nouveau parser, writer, format M7, migration ou dépendance.
Le port PublicationStore expose en complément les numéros occupés et les détails
du plan historique. Le builder et les protocoles d’engagement M6/M7 sont inchangés.

## IPC et protections

| Host Tauri | IPC privé | Paramètres utiles |
| --- | --- | --- |
| `publication_query` | `publication_history`, `publication_prepare` | UUID collection, offset |
| `publication_query` | `publication_details` | UUID, version, offset |
| `publication_query` | `publication_status`, `publication_verify` | UUID, version |
| `publish_version` | `publication_publish` | UUID, version, capacité du résumé |
| `rebuild_publication` | `publication_rebuild` | UUID/version ; destination réservée au host |

Validation stricte aux deux frontières : UUID, versions entières 1–999999, offset
0–1 000 000, capacité hexadécimale de 48 caractères, aucun champ supplémentaire.
L’enveloppe IPC v1 conserve ses bornes 16 Kio / 2 Mio. Historique et composants
sont paginés par 50 ; libellés bornés à 256 caractères. Le résumé affiche les types
traduits des WARNING acceptés (100 types au plus), sans recopier un rapport modifiable.
Les détails techniques montrent au plus 100 noms de sorties et leur nombre total.

Les mutations sont refusées readonly, pendant une préparation active et après
restauration avant redémarrage. Le host vérifie aussi le mode et l’ingestion avant
envoi. Le sidecar revérifie ces préconditions. Aucune destination ou manifest ne
vient de la WebView : le sélecteur natif parenté choisit un dossier parent ; le host
propose un sous-dossier neuf `FabParts-vNNNNNN-<horloge>`. Une collision est refusée.
Les protections M7 contre écrasement, données locales et bibliothèques sources
restent actives ; le pont protège aussi le home personnel et les données historiques.

Délais dédiés : publication/reconstruction 600 s ; préparation, historique et
vérification 300 s ; statut/détails 60 s. Les commandes ordinaires gardent 8 s.
L’interface reste asynchrone, affiche l’opération active et suspend ses heartbeats.

## Parcours et garanties

Depuis une bibliothèque : **Publications KiCad** affiche le nom, le nombre de
composants, la qualification actuelle de Collection, le prochain numéro et
l’historique daté. Un rapport Part ne qualifie jamais la Collection. Absence de
rapport, STALE, ERROR ou WARNING non accepté bloquent la préparation, avec accès
au rapport de bibliothèque TECH-04B.

Le résumé expose composants, ressources/origines, version, qualification et WARNING.
Une case initialement vide précède **Confirmer et publier**. La capacité éphémère
est liée au plan, au rapport exact et au numéro ; tout changement impose une
nouvelle revue. Les refus du builder, notamment les liens 3D non résolus, restent
bloquants même après acceptation des WARNING. Aucun asset canonique ni bibliothèque
officielle n’est modifié.

Le numéro proposé est supérieur à tous les numéros présents, y compris les dossiers
sans COMMIT. Ceux-ci restent réservés et ne figurent jamais comme publications
valides. Aucun manifest, COMMIT ni numéro occupé n’est remplacé.

Avant envoi, l’interface conserve une demande minimale (espace, collection, version,
empreinte). Après succès **ou erreur**, elle consulte l’engagement M7 durable avant
d’annoncer un résultat. Une réponse incertaine bloque toute nouvelle publication ;
**Reconnecter et vérifier le résultat** relance le moteur puis consulte le statut,
sans renvoyer la mutation. Un autre espace/copie ne peut pas acquitter cette demande.
COMMITTED exige un manifest/COMMIT cohérent et une empreinte correspondant au résumé ;
ABSENT et RESERVED ne sont jamais présentés comme un succès. Le journal UI ne fait
pas autorité sur les données et ne remplace aucun mécanisme M7.

L’historique dit **Non vérifiée** jusqu’à la vérification effective des inputs et
artefacts. Le résultat PASS est ponctuel, en mémoire, remis à zéro à l’actualisation
ou au redémarrage. Les détails et la reconstruction relisent le plan figé, sans
catalogue courant. La reconstruction compare tous les fichiers et hashes historiques
avant exposition ; elle ne répare pas silencieusement l’ancienne publication.
Les sorties sont uniquement destinées à une intégration **de projet** `${KIPRJMOD}`.

## Vérifications

- pytest complet avec `FABPARTS_TEST_FREECAD=1` : **556 réussis**, aucun ignoré.
- Ruff, format et mypy : succès ; 177 modules contrôlés par mypy.
- Rust : **29 réussis** ; rustfmt conforme.
- Frontend TECH : **68 réussis** ; frontend UX : **12 réussis**.
- Svelte check : **0 erreur / 0 avertissement**.
- Sidecar PyInstaller et paquet Tauri release macOS ARM64 construits ; seul
  l’avertissement Vite hérité sur la taille de chunk demeure.

Les nouveaux tests du pont couvrent confirmation exacte, PASS, WARNING accepté,
refus absent/STALE/ERROR/WARNING, numéro incomplet réservé, résultat retrouvé après
perte de réponse, immutabilité, reconstruction figée, readonly réel et gardes
BUSY/restauration. Le test du refus 3D confirme qu’une acceptation M5 ne contourne
pas le builder. Les tests M7 existants couvrent aussi concurrence, corruption du
manifest/COMMIT/input/artefact, panne au COMMIT, reconstruction sans sources courantes,
références officielles et builder incompatible. Le test complet TECH-04A sauvegarde,
restaure puis vérifie une vraie publication avec ses inputs. Ingestion, validation,
migrations et quatre previews restent couverts par la suite complète.

Les tests frontend vérifient confirmation non précochée, double clic, perte de
réponse après COMMIT sans second envoi, engagement inconnu conservé, reconnexion,
numéro réservé/absent, conflit d’empreinte, copie d’un autre espace, vérification
en échec fermeture de vue avec réponse tardive et diagnostic du builder conservé après
confirmation de l’absence de COMMIT.

## Inspection native et KiCad

Paquet release et sidecar embarqué utilisés sur bibliothèques synthétiques. Inspection
Computer Use en FR/EN, clair/sombre, fenêtre normale 1440×900 points et réduite à
environ 901×949. Résumé, états désactivés, focus, confirmation, historique et actions
restent accessibles. Le libellé readonly affiché à tort pendant la préparation a été
corrigé. Le sélecteur de reconstruction est rattaché à la fenêtre principale.

Parcours observés : LabParts PASS publie v2 après confirmation ; v1 reste intacte,
montre son ancien nom malgré le catalogue modifié et se reconstruit par le sélecteur
natif. PersonalParts WARNING bloque d’abord, conduit au rapport Collection, puis
publie après revue/acceptation et confirmation distinctes. La fermeture/réouverture
conserve l’historique et remet l’intégrité à Non vérifiée. La copie native readonly
permet lecture/vérification et n’expose ni publication ni reconstruction.
Un dernier test du sidecar réellement embarqué confirme deux versions LabParts,
v1 vérifiée PASS et Qt absent. Ses **37 fichiers** readonly sont inchangés ; les **9 fichiers historiques** sont inchangés,
et le dossier système FabParts reste absent comme au début.

Les **six sorties** reconstruites de v1 correspondent exactement à l’inventaire
SHA-256/taille historique. **KiCad 10.0.7**, via `kicad-cli sym export svg` et
`fp export svg`, a relu ces bibliothèques et produit les SVG attendus dans les seuls
dossiers de test, avec configuration isolée. Aucun projet réel ni table globale
n’a été ouvert ou modifié. Ce contrôle est une lecture par le moteur KiCad installé,
pas une qualification interactive d’un projet complet.

Captures natives :

- [Historique sombre et intégrité ponctuelle](tech05a/history-dark.jpg)
- [Confirmation vide et WARNING accepté, clair réduit](tech05a/confirmation-light-narrow.jpg)
- [Publication WARNING confirmée, anglais](tech05a/published-warning-light-en.jpg)

## Checkpoint et limites

**GO WITH CONDITIONS** : macOS ARM64 qualifié ; couverture M5 structurelle partielle,
aucune certification électrique/mécanique exhaustive. Les grandes collections et
historiques sont traités synchroniquement et sérialisés côté moteur ; les délais
restent bornés. Aucun arrêt électrique réel n’est qualifié. Une corruption de
manifest bloque explicitement la lecture de l’historique concerné ; restauration
vérifiée requise, sans réparation automatique. Les limites TECH-04A restent applicables.

L’immutabilité reste celle des API M7, avec détection de corruption par hashes ;
elle ne protège pas contre une modification externe malveillante. La demande UI
persistée suppose le stockage local WebView disponible ; si son écriture échoue,
la publication n’est pas envoyée. Le vérifier/reconstruire ne certifie pas un projet.
Les formats source exigent une version KiCad compatible, sans downgrade.

Données de test, publications, SVG de contrôle et exécutables restent ignorés par Git.
Seules les captures documentaires sont suivies. PR vers main sans merge automatique.
Aucune installation globale, synchronisation, activation ou rollback : **TECH-05B
non commencé. Arrêt au checkpoint TECH-05A.**
