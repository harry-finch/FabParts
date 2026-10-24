# Legacy Python desktop — KiPart Manager

This guide describes the existing PySide6 application. It does not describe the read-only Tauri prototype.

Electronic component manager — anciennement KiPart Manager.

Gestionnaire desktop local-first de composants électroniques, d'assets, de stocks
et de bibliothèques KiCad. Le cœur fonctionne sans Internet, serveur ni IA.

M6 ajoute la construction de bibliothèques KiCad au catalogue, aux stocks,
au resolver et à l’Asset Store. Ce dernier importe et restitue PDF, STEP/STP,
WRL, `.kicad_mod` et `.kicad_sym`.
L'interface est organisée autour de six espaces : **Composants**, **Inventaire**,
**Bibliothèques**, **KiCad local**, **Publications** et **Paramètres**. La fiche composant
relie package, ressources choisies, quantités et qualification. Les packages et
fichiers restent accessibles dans Composants ; quantités et emplacements dans
Inventaire ; les Collections métier sont présentées comme Bibliothèques.
Le choix des ressources reste explicite et les rapports PASS/WARNING/ERROR sont
soumis aux règles existantes. Voir [les conventions UI](UI_GUIDELINES.md).

M7 conserve des versions immuables par collection, avec manifest, dépendances,
vérification des hashes et reconstruction indépendante du catalogue courant.
Voir [le guide M7](PUBLICATIONS.md).
M8 livre le transfert portable `.kiparts` et termine le MVP. M9 ajoute une
recherche officielle KiCad distante **optionnelle et désactivée par défaut**.
Voir [le guide M9](REMOTE_KICAD.md).
M10 ajoute identification traçable, comparaison des propositions et conservation
de plusieurs datasheets. Le téléchargement constructeur est facultatif, avec
domaines autorisés explicitement et aucun domaine préautorisé. Voir
[le guide M10](DOCUMENTATION.md).

M10.5 prépare le resolver SnapMagic optionnel, l’import et la provenance durable.
**La connexion API réelle attend le contrat partenaire ; les recherches sont
vérifiées avec un fournisseur simulé uniquement dans les tests.** Voir
[le guide M10.5](SNAPMAGIC.md).

M11 ajoute une assistance d’identification facultative : Gemini natif, Ollama local
et API compatible OpenAI. Contexte relu avant chaque envoi, suggestions comparées
et acceptées par champ avec provenance M10 ; fournisseur désactivé par défaut.
Voir [configuration Gemini/Ollama](ASSISTANCE.md).

UX A1 ajoute les aperçus locaux de symboles, footprints et PDF, avec zoom,
provenance et aide contextuelle. Voir [les aperçus](ASSET_PREVIEWS.md) et
les fonctions de navigation intégrées. A2 ajoute l’inspection 3D WRL et STEP (FreeCAD local facultatif pour STEP),
avec rotation, zoom et vues standard : inspection locale.

L’interface suit désormais le pack **Professional Workshop UI** : thème sombre,
contrôles compacts, inspecteurs contextuels et accès direct à l’assistance existante.
Voir [les conventions UI](UI_GUIDELINES.md).

## Installation de développement

Python 3.12+ et un environnement desktop compatible Qt sont requis. Depuis la
racine du dépôt, sur macOS/Linux :

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-build-isolation --no-deps -e '.[dev]'
python -m pip check
```

Sous Windows, créer l'environnement avec `py -3 -m venv .venv` puis l'activer
avec `.venv\Scripts\Activate.ps1` ; les commandes `python` restent identiques.
Vérifier que l'interpréteur choisi est au moins Python 3.12.

`requirements-dev.lock` fige les versions testées en M6 (Python 3.13.9,
macOS arm64). Il ne garantit pas la disponibilité des wheels sur tous les OS ;
PySide6 6.12 installé ici requiert macOS 14+. Les autres plateformes et Python
3.12/3.14 restent à vérifier. Pour résoudre de nouvelles versions compatibles
avec les plages de `pyproject.toml`, utiliser `python -m pip install -e '.[dev]'`,
puis revalider et mettre à jour le fichier de versions volontairement.
L'installation initiale télécharge les dépendances ; l'application n'utilise
aucun réseau pour son cœur. Les actions M9 explicitement activées utilisent
GitLab ; M10 contacte uniquement les domaines constructeurs autorisés pour
un téléchargement demandé. Ne pas versionner `.venv`.

## Lancement

```sh
kipartmanager
# Ou :
python -m kipartmanager
# Vérification sans ouvrir Qt :
kipartmanager --version
```

La fenêtre se ferme avec son bouton de fermeture. Au démarrage, Alembic met à
jour la base locale, puis initialise Lab/Personal et LabParts/PersonalParts sans
doublons et sans réinitialiser les modifications existantes.

Par défaut, les données résident dans le dossier `AppLocalDataLocation` de Qt,
dans `database/catalogue.sqlite3` (sur macOS généralement sous
`~/Library/Application Support/KiPart Manager`). Pour choisir un dossier :

```sh
kipartmanager --data-dir ./local-data
```

Ce dossier contient vos données : sauvegarder ensemble `database/`, `assets/` et `publications/`
après fermeture de l'application. `local-data/`
est ignoré par Git ; pour d'autres chemins, utiliser un emplacement hors du dépôt
ou adapter les exclusions locales. `--help` et `--version` ne créent pas de base.
Les migrations sont embarquées dans le package ; aucune commande Alembic externe
ni installation serveur n'est nécessaire au lancement. Ne pas modifier la base
manuellement. Le downgrade initial est destructif et réservé aux tests jetables.

Chaque page du catalogue permet de créer et de modifier la sélection. Créer d'abord les
assets (métadonnées), packages et localisations, puis les composants et stocks
qui les référencent. Les collections utilisent des cases à cocher pour leurs
composants ; les composants et packages pour leurs assets. Les assets restent
`UNCHECKED` globalement : les rapports M5 qualifient une Part ou Collection
pour des contrôles définis, sans certifier intégralement chaque format.

Dans **Composants → Fichiers & ressources** :

- **Importer un fichier** crée un nouvel asset, avec nom et provenance explicites.
- **Associer un fichier** complète une fiche sans fichier, en conservant son UUID
  et sa provenance. Le format doit correspondre au type de la fiche.
- **Vérifier l'intégrité** recalcule SHA-256 et contrôle la taille.
- **Restituer une copie** écrit une copie vérifiée hors du store ; une destination
  existante est refusée. Le fichier canonique reste dans le store.

Le store déduplique les octets sous `assets/blobs/<préfixe>/<sha256>`. Deux imports
identiques gardent leurs UUID, noms et provenances distincts, avec un seul blob.
Un fichier déjà associé n'est jamais remplacé ou détaché ; importer un nouvel
asset pour proposer une autre ressource. Les sources ne sont pas modifiées.

M2 accepte les extensions prévues (sans distinction de casse) et les fichiers
non vides, puis conserve leurs octets. Cela ne vérifie ni la validité d'un PDF,
ni la syntaxe KiCad, ni la géométrie STEP/WRL : M5 réalise des contrôles
explicites et limités, décrits ci-dessous. Une intégrité correcte ne signifie pas une validation sémantique.

Une interruption peut laisser un temporaire dans `assets/.staging/`, ignoré par
le catalogue, ou un blob complet non référencé, réutilisé au prochain import du
même contenu. Aucun nettoyage automatique ne risque de supprimer un import en
cours. Après une interruption, relancer l'import et vérifier l'intégrité des
assets concernés. Une corruption ou un fichier absent est signalé et bloque la
restitution ; le store ne remplace pas automatiquement un blob corrompu.
La publication exclusive utilise les liens physiques du filesystem ; un volume
qui ne les supporte pas provoque une erreur explicite. Les opérations sont
synchrones : un gros fichier peut immobiliser temporairement la fenêtre.

Un stock est un entier de 0 à 2⁶³−1, unique par composant/inventaire, avec une
localisation facultative. Le stock nul ne supprime pas le composant et n'empêche
pas de l'ajouter à une collection. Aucun mécanisme de suppression n'est fourni.

## Index KiCad local

Dans **KiCad local**, découvrir ou saisir les dossiers `symbols`, `footprints`
et `3dmodels`, enregistrer puis reconstruire. Rechercher ensuite par nom ou
métadonnées, avec un filtre de type. Le scan se fait en arrière-plan et aucune
bibliothèque n'est modifiée ou copiée vers les assets. Attendre sa fin avant
fermeture. Sans installation KiCad, le catalogue reste utilisable.

Configuration : `config/kicad.toml` ; cache reconstruisible : `index/kicad.sqlite3`.
La recherche lit exclusivement le cache, sans réseau. Les références externes
restent distinctes des assets gérés ; M4 permet de les sélectionner explicitement.
Voir [Index KiCad](KICAD_INDEX.md) pour les formats KiCad 6–10, les limites,
la découverte, les identifiants portables et le traitement des erreurs.

## Résolution locale

Sélectionner une fiche dans **Composants** ou **Composants → Packages partagés**, puis **Résoudre les
ressources locales**. Rechercher par rôle, comparer les candidats utilisateur,
gérés et officiels, sélectionner une ligne puis enregistrer le choix. Changer un
choix existant requiert la case de confirmation ; les anciens fichiers et liens
restent conservés. Les choix mécaniques concernent le Package partagé.

Sans KiCad ou sans résultat, les choix précédents restent conservés. Les assets
sans fichier ou corrompus sont signalés. Voir [Resolver local](LOCAL_RESOLVER.md)
pour les rôles, la migration, les garanties de concurrence et les limites.

## Validation locale

Dans **Composants** ou **Bibliothèques**, sélectionner une fiche et cliquer sur
**Valider le composant** (ou **Valider localement** dans Bibliothèques),
puis **Exécuter les contrôles locaux**. Le rapport affiche
les résultats, identifiants des ressources et SHA-256. Un Package et des choix
explicites de symbole/footprint sont requis pour la qualification PCB.

ERROR bloque la qualification de collection. Pour les WARNING, examiner le rapport,
cocher l'acceptation puis relancer les contrôles sur ces mêmes données. Un changement
pertinent rend le rapport STALE ; **Vérifier si le rapport est toujours actuel**
relit les données et fichiers. Une nouvelle validation est alors nécessaire.
Les contrôles 3D et PDF restent partiels et produisent un WARNING explicite.
Voir [Validation locale](VALIDATION.md) pour les règles et limites. M5 fournit
le blocage métier utilisé par le publisher M6.

## Construction des bibliothèques KiCad

Dans **Bibliothèques**, sélectionner LabParts, PersonalParts ou une autre collection
qualifiée, puis **Exporter pour KiCad**. Choisir un nouveau dossier
hors des données et bibliothèques sources. La sortie contient symboles, footprints,
modèles/PDF choisis, tables de projet et instructions ; aucun fichier existant
n'est écrasé. Les liens utilisent `${KIPRJMOD}` : intégrer au dossier projet KiCad
selon `UTILISATION.txt`, en ajoutant les entrées aux tables existantes.

M6 fournit un mode de copie autonome. Les ressources officielles sont copiées seulement
dans la sortie, avec leurs identités/provenances conservées. Les dépendances 3D
ambiguës bloquent la construction, même après acceptation d'un WARNING M5. Un
marqueur BUILDING indique une sortie incomplète après interruption. Voir le
[guide du publisher](PUBLISHER.md) pour liens, compatibilité et garanties.
Ce sont des artefacts de l'état courant. Pour figer une version historique, utiliser
**Publications** et le [guide M7](PUBLICATIONS.md).

## Tests, qualité et packaging

```sh
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m build --no-isolation
```

Ruff assure lint et formatage ; mypy contrôle le typage strict. Pour appliquer le
formatage : `python -m ruff format .`. pytest vérifie les imports, les points
d'entrée installés, les frontières des couches et le lancement/fermeture Qt dans
un sous-processus `offscreen`, avec connexions réseau Python interdites.
Les tests couvrent aussi migrations M1→M2→M4→M5, contraintes, rollback, réouverture,
les cinq formats, doublons/provenance, corruption, erreurs d'accès, destinations
concurrentes et interruptions de processus, ainsi que les formulaires et actions Qt. L’index ajoute parsing, métadonnées,
reconstruction reproductible, lecture seule, erreurs et parcours Qt hors ligne.
Le resolver couvre priorité, choix explicite, concurrence, rollback et maintien
des fichiers/associations/sélections après redémarrage. M5 couvre pins/pads,
formats malformés, rapports persistés, acceptation explicite des WARNING,
invalidation et blocage des collections, avec parcours Qt sans réseau. M6 vérifie
reconstruction, héritage, liens portables, copies, protection des destinations et
changements pendant construction ; les ressources sources restent préservées.
M7 couvre engagement, versions concurrentes, corruptions et reconstruction historique
après modification du catalogue et disparition des sources courantes/officielles.
Ce smoke test exige les bibliothèques natives Qt mais pas de serveur d'affichage ;
il ne remplace pas une vérification visuelle sur chaque plateforme supportée.

Le build produit un sdist et une wheel dans `dist/` (ignoré par Git).
Ils embarquent le logo approuvé et ses dérivés PNG/ICO/ICNS. Sources, régénération,
intégration Qt et limites du packaging desktop : [identité graphique](BRANDING.md).
Le backend standard setuptools utilise les métadonnées de
[`pyproject.toml`](../pyproject.toml), et la version vient de `kipartmanager.__version__`.
La configuration des outils est centralisée dans ce fichier TOML ; `--data-dir` choisit la racine et M3 conserve les chemins KiCad en TOML.

## Structure et documentation

```text
src/kipartmanager/
  __main__.py       # lancement module
  bootstrap.py      # point de composition et lancement Qt
  domain/           # entités, règles et identité des fichiers
  application/      # catalogue, fichiers et index KiCad
  ports/            # catalogue, Asset Store et index
  infrastructure/   # SQLite, migrations, store, parsing et découverte KiCad
  ui/               # onglets, formulaires et actions fichiers
tests/
```

- [Spécification produit](PROJECT_SPEC.md) : besoins, vocabulaire et invariants.
- [Architecture](ARCHITECTURE.md) : responsabilités, dépendances et stockage.
- [Milestones](MILESTONES.md) : périmètres, acceptation et checkpoints.
- [Instructions du dépôt](../AGENTS.md) : règles persistantes de développement.

Une milestone à la fois ; chaque checkpoint se termine par un arrêt.

- [Publications M7](PUBLICATIONS.md) : manifests et reconstruction historique.

### Transférer une bibliothèque

Dans **Publications**, sélectionnez une version puis exportez-la en **.kiparts**.
Sur une autre installation, importez l’archive après examen des conflits, puis
reconstruisez la version dans un dossier projet KiCad neuf. Le transfert fonctionne
hors ligne et conserve les sources figées, hashes et versions. Les stocks restent
locaux et les composants importés demandent une nouvelle qualification.
Voir [le format et la politique de conflits](KIPARTS.md).
