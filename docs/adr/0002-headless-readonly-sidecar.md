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
