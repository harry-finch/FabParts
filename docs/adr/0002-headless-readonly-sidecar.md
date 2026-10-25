# ADR 0002 — Lecture du catalogue par sidecar privé dans TECH-01

Date : 24 octobre 2026. Statut : retenu pour le prototype TECH-01 uniquement.

## Contexte

L’option B de l’audit doit être éprouvée sans réécrire le moteur ni exposer les
données de production à une migration. Le bootstrap PySide6 migre le schéma,
initialise des collections et compose des adaptateurs qui peuvent créer des fichiers.

## Décision

Un nouveau point d’entrée `kipartmanager.headless` compose `Catalogue`,
`SqliteCatalogue` et `SqliteDocumentation`. Le domaine et le bootstrap actuel
restent inchangés. `CatalogueReader` projette leurs lectures vers des DTO explicites.
L’adaptateur entrant `headless_ipc` reste à la racine de composition :
l’infrastructure ne dépend pas de l’application.

Le sidecar n’ouvre qu’un dossier explicitement choisi, marqué comme copie TECH-01,
avec le schéma `0007_asset_provenance`. SQLite utilise `mode=ro&immutable=1`,
`query_only` et un authorizer refusant écritures, DDL et ATTACH. La copie doit être
figée, sans WAL/journal actif. Aucune migration, initialisation, indexation ou
lecture de fichiers KiCad externes au démarrage. Le marqueur évite les ouvertures
accidentelles ; il n’est pas une frontière de sécurité contre un utilisateur local
capable de modifier les fichiers. La garantie d’absence d’écriture repose aussi
sur SQLite et sur la comparaison des empreintes avant/après les essais.

Le protocole JSONL v1 sur stdin/stdout est privé, borné et corrélé. Quatre commandes
métier de lecture sont autorisées. `shutdown` est un contrôle de cycle de vie interne.
Les logs vont sur stderr. Rust détient le processus et le transport, pas les règles
métier. Une seule requête est active ; une réponse périmée ne doit pas contaminer
une session suivante. Le timeout ferme la session et exige un redémarrage explicite.

Tauri embarque un exécutable PyInstaller via `bundle.externalBin`, suffixé par
le target triple lors du build. Le plugin shell s’utilise exclusivement depuis Rust.
La WebView a cinq permissions de commandes typées, aucune permission shell ou
filesystem. Le chemin de la copie est fourni en argument de lancement ou dans
l’état initial de connexion du POC ; il ne désigne jamais implicitement la production.

Le frontend importe directement les styles, thèmes et primitives du prototype UX 02.
Sa projection des données est propre à TECH-01 ; aucun import des fixtures du
catalogue UX, aucune substitution silencieuse si le moteur échoue. L’état métier
DRAFT/IDENTIFIED/DEPRECATED n’est pas converti en préparation schéma/PCB.

## Conséquences et limites

Les associations, choix externes et métadonnées se consultent sans Qt, Internet,
KiCad installé ou provider IA. L’Asset Store n’est pas initialisé ; ses métadonnées
sont lues dans le catalogue. Les octets, aperçus et rapports de qualification ne
sont pas vérifiés par ce POC. Les ressources conservent leur état connu UNCHECKED ;
un choix ne vaut pas qualification.

L’adaptateur de lecture charge les petites listes existantes et applique les filtres
en mémoire. La pagination borne le transport, pas le coût total des requêtes.
L’optimisation, les tâches longues, les écritures transactionnelles, les migrations
en production et le packaging multi-OS ne sont pas décidés par cet ADR.

Les preuves de développement antérieures au snapshot public sont conservées en privé.

## Stabilisation TECH-01B — 24 octobre 2026

Les frontières et le protocole v1 sont conservés. Le démarrage dispose de 30 s,
les lectures de 8 s. Un signal local de fermeture annule les attentes Rust et
interdit un nouveau démarrage après fermeture. L’arrêt coopératif dispose de 2 s,
puis le groupe est arrêté si nécessaire. Les diagnostics stderr sont limités à
une liste de champs de processus/transport ; paramètres et résultats métier
ne sont jamais journalisés. Le harnais utilise ces identités et conserve chaque
exécution séparément.

## Extension TECH-02A — 25 octobre 2026

Les commandes additives `get_asset_preview`, `read_pdf_chunk` et `release_preview`
conservent JSONL v1. Rust valide UUID/rôles et handles/offsets, puis sérialise les
lectures dans la session existante. Un handle PDF n’est lisible que s’il a été
retourné par cette session. Les limites et l’annulation de fermeture restent actives.

`AssetPreviews` résout les sélections et associations métier avant `Previews`.
`ReadonlyPreviews` implémente le port existant ; il lit uniquement le store de la
copie ou les racines de sa configuration KiCad, avec contrôle SHA-256. Aucun import,
index, migration, écriture ou découverte automatique au démarrage. Le parseur
`kicad_preview` et les DTO neutres sont réutilisés. L’infrastructure continue de
dépendre des ports et du domaine, pas de l’application.

PDF.js embarqué remplace QtPdf uniquement dans ce frontend. Un worker local lit
un snapshot transféré par blocs de 64 Kio, limité à 16 Mio, via un handle aléatoire
valable 120 s. Deux snapshots maximum en mémoire Python ; libération après transfert,
à l’expiration lors de la prochaine commande, ou à la fermeture. Aucun fichier
temporaire, URL distante, accès filesystem JavaScript ou couche de scripts PDF.
Les polices standard et CMaps sont locales. Le rendu natif WebView a été écarté
pour son comportement variable selon l’OS ; un moteur Python de rasterisation
ajouterait une dépendance native et du transport d’images. Le choix ne change pas
le viewer historique QtPdf ni les formats de stockage.

Les dessins sont rendus en SVG échappé par Svelte, sans HTML issu des fichiers.
Le cache de quatre géométries est indexé par SHA/type/symbole et le hash du fichier
est revérifié avant réutilisation. Zoom/couches/unités ne relancent pas le parseur.
Une prévisualisation ne change jamais les qualifications. Voir le
[checkpoint TECH-02A](../FABPARTS_2_TECH_02A.md) pour les bornes et preuves.

## Extension TECH-02B — aperçus 3D interactifs

`get_asset_preview(role=MODEL_3D)` résout le choix métier puis confie un snapshot
vérifié à `ModelJobs`. Ce service applicatif possède un seul worker et deux jobs
maximum ; il dépend du port `MeshConverter`, jamais de FreeCAD ou du filesystem.
Le worker n'utilise pas le catalogue/SQLite. Le port est composé avec le parseur
WRL existant et l'adaptateur FreeCAD externe dans `headless.py`.

`get_model_status`, `read_mesh_chunk` et `release_model_preview` sont additifs à
IPC v1. Le timeout des commandes reste 8 s ; seule la conversion externe dispose
de 30 s, hors boucle de lecture IPC. Le résultat FPM1 est un snapshot binaire
borné avec SHA-256, transféré en blocs de 64 Kio par handle de session, sans chemin
fourni par la WebView. Registres PDF et 3D séparés ; annulation, expiration et
redémarrage invalident les résultats. `PreviewBuffers` mutualise uniquement la
mécanique de snapshots, pas les autorisations ni les quotas des deux types.

Three.js/OrbitControls (MIT) rend le DTO neutre dans Svelte, à la demande. FreeCAD
reste facultatif et externe ; WRL fonctionne sans lui. Aucun runtime CAO, Qt,
service réseau ou droit filesystem WebView supplémentaire n'est embarqué.
Les bornes, limitations géométriques et réserves multiplateformes sont détaillées
dans [TECH-02B](../FABPARTS_2_TECH_02B.md).
