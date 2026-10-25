# FabParts TECH-01 / TECH-01B / TECH-02A

Prototype local en lecture seule : Svelte 5 → Tauri 2 → sidecar Python JSONL →
services existants → copie figée SQLite. UX 02 reste intact dans `../fabparts-ux`.
Le moteur historique PySide6 n’est pas modifié.

## Construire

Prérequis : Python 3.12+ et `.venv` du projet, PyInstaller 6.16.0, Node/npm,
Rust **1.90.0**, outils natifs macOS. Python 3.13 et macOS ARM64 sont utilisés ici.
`rust-toolchain.toml` fixe Rust ; les dépendances npm et Cargo sont verrouillées.
L’installation des outils peut nécessiter Internet ; l’application n’en a pas besoin.

Depuis la racine du dépôt :

```sh
./prototypes/fabparts-tech-01/scripts/install-build-tools.sh
rustup run 1.90.0 sh ./prototypes/fabparts-tech-01/scripts/build-desktop.sh --offline
```

`--offline` suppose les caches déjà alimentés par l’installation. Le script
construit le sidecar, vérifie Svelte/tests et construit le paquet release avec
`Cargo.lock`. Pour construire seulement le moteur :

```sh
rustup run 1.90.0 sh ./prototypes/fabparts-tech-01/scripts/build-sidecar.sh
```

Paquet : `src-tauri/target/release/bundle/macos/FabParts TECH-01.app`.
Il embarque le runtime Python, sans Qt ; aucun `.venv` n’est nécessaire à son
exécution. Binaires/caches/données privés sont exclus de Git. Pas de signature
Developer ID, notarisation ni qualification Windows/Linux.

## Préparer une copie

Fermer KiPart Manager pendant la copie. Ne jamais ouvrir la production avec ce POC.
Le script refuse une destination existante, les liens symboliques et les journaux
SQLite actifs. Il copie le dossier complet, sauvegarde SQLite via `backup`, vérifie
son intégrité et les empreintes source. Les ressources KiCad externes restent des
références, pas une sauvegarde de l’installation KiCad.

```sh
.venv/bin/python prototypes/fabparts-tech-01/scripts/prepare-copy.py \
  --source '/chemin/du/dossier/de/donnees' \
  --destination "$PWD/local-data/ma-copie-tech01"
```

La copie doit rester figée, avec son marqueur `TECH01_COPY.json` et le schéma
`0007_asset_provenance`. Aucune migration n’est exécutée.

## Lancer

```sh
open 'prototypes/fabparts-tech-01/src-tauri/target/release/bundle/macos/FabParts TECH-01.app' \
  --args --data-dir "$PWD/local-data/ma-copie-tech01"
```

Sans argument, l’écran de connexion demande explicitement le chemin d’une copie.
Il n’existe pas de chemin de production par défaut. Le choix reste en mémoire pour
la session. Une copie absente/incompatible produit un état d’erreur, jamais une démo.

Développement, depuis le dossier du prototype :

```sh
cd prototypes/fabparts-tech-01
rustup run 1.90.0 npm run tauri -- dev --no-watch --no-dev-server \
  --features custom-protocol -- -- --data-dir '/chemin/absolu/de/la/copie'
```

Les deux séparateurs après les options Tauri séparent les options de compilation
et celles de l’application. Le hook compile Svelte et attend sa fin (`wait: true`) avant de lancer Rust ; aucune URL de serveur local
n’est nécessaire. Le mode sans watch demande une relance après modification.
`npm run dev` seul ne connecte pas le moteur et ne lit aucune base.

## Vérifier le paquet et le cycle de vie

Fermer les anciennes instances avant les essais. Depuis la racine :

```sh
./prototypes/fabparts-tech-01/scripts/verify-native.sh --cycles 3
rustup run 1.90.0 sh ./prototypes/fabparts-tech-01/scripts/verify-native.sh --mode dev --cycles 1
```

Ce même point d’entrée vérifie d’abord le sidecar embarqué avec un environnement
sans PATH/PYTHONPATH/PYTHONHOME, puis ouvre sa propre instance pour chaque cycle.
Il utilise uniquement `local-data/fabparts-tech01/catalogue-copy`. Le harnais Python
requiert `.venv` ; l’application et son sidecar packagé n’en dépendent pas.

Chaque cycle guide recherche/sélection, indisponibilité après interruption volontaire,
redémarrage, retour du catalogue et fermeture ⌘Q. Les PID sont annoncés par Rust ;
le harnais vérifie parenté et groupe isolé avant tout signal. La fermeture contrôle
**tous** les groupes observés. Chaque tentative conserve logs et JSON dans un nouveau
sous-dossier de `local-data/fabparts-tech01b/runs/`. Un échec arrête la série sans
fermer silencieusement une fenêtre ; conserver son journal et fermer cette instance
avant de reprendre. Ne pas interpréter un PASS isolé comme une garantie universelle.

Logs runtime sur stderr : lancement, PID parent/sidecar/worker, groupe, état, code
IPC, durée et fermeture. `FABPARTS_DIAGNOSTICS=1` ajoute les succès de commandes pour
le harnais, sans paramètres ni résultats du catalogue. Les sondes `health` réussies
ne sont pas journalisées en boucle. Le démarrage a un délai de 30 s ; les requêtes,
8 s. Une fermeture annule les attentes ; l’arrêt coopératif dispose de 2 s avant
l’arrêt du groupe. Aucune relance automatique.

## Contrôles automatisés

Depuis la racine :

```sh
.venv/bin/pytest -q
.venv/bin/ruff check src tests prototypes/fabparts-tech-01/scripts
.venv/bin/ruff format --check src tests prototypes/fabparts-tech-01/scripts
.venv/bin/mypy src tests
npm --prefix prototypes/fabparts-tech-01 run check
npm --prefix prototypes/fabparts-tech-01 test
npm --prefix prototypes/fabparts-tech-01 run build
npm --prefix prototypes/fabparts-ux run check
npm --prefix prototypes/fabparts-ux test
npm --prefix prototypes/fabparts-ux run build
rustup run 1.90.0 cargo test --locked --offline --manifest-path prototypes/fabparts-tech-01/src-tauri/Cargo.toml
rustfmt --edition 2021 --check prototypes/fabparts-tech-01/src-tauri/src/*.rs
```

Les faux transports sont exclusivement dans les tests. L’application n’importe
aucun catalogue ou aperçu de démonstration. Le mode natif nécessite une session
graphique et des permissions de processus que certains bacs à sable interdisent.

La validation native antérieure couvre macOS ARM64 uniquement. Les rapports et captures internes ne sont pas distribués ; les commandes ci-dessus permettent de reproduire les contrôles avec ses propres données de développement.

## Real previews — TECH-02A

Symbol and footprint drawings use the existing Python parser. PDFs use a locally
bundled PDF.js worker, with CMaps/fonts copied by Vite. No Qt is needed in the
sidecar. Run `npm ci` before building to install the locked PDF.js dependency.

Create a **new disposable** catalogue with original redistributable test files:

```sh
PYTHONPATH=src .venv/bin/python -m tests.preview_corpus /tmp/fabparts-tech02-copy
# Add --official only to also reference the installed KiCad NE555P and DIP-8.
```

Open the package and enter that directory in its copy selector. The script refuses
an existing output directory and never opens production data. Use “Open details”
to see the four resource cards. The preview menu inspects an association without
changing the selected resource. See [TECH-02A](../../docs/FABPARTS_2_TECH_02A.md)
for contracts, corpus, bounds, tests and native screenshots.
