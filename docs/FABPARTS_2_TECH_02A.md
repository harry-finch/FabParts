# FabParts 2.0 — TECH-02A

25 octobre 2026. Branche `tech/02a-real-asset-previews`.

## Décision

**GO WITH CONDITIONS** pour la revue Product Owner : aperçus réels 2D/PDF connectés,
inspection native macOS ARM64 effectuée. Les limites de fidélité KiCad et PDF sont
explicites ci-dessous. Windows/Linux, distribution signée et fidélité exhaustive
ne sont pas validés. TECH-02B et TECH-03 ne sont pas démarrés.

## Préparation et audit

Le checkout public part du `main` consolidé `29a2f1e1fbd7c033b7775ac0cf7a2cd42a977bd4`,
synchronisé avec `origin` (`harry-finch/FabParts`), sans changement local initial.
La branche est créée avant l’implémentation. Les dossiers, rapports GIT-01 à GIT-04
et l’historique antérieur restent dans l’archive privée ; ils ne sont ni remplacés
ni réintroduits dans le dépôt public. Les données de travail et paquets sont ignorés.

Références : AGENTS, architecture, UX_SPEC, UI_GUIDELINES, audit/TECH-01/TECH-01B
privés, ADR 0002 et prototypes UX 02/TECH-01B. Skills inspectées : fab-design-system,
professional-workshop-ui, kicad-library-workflow, verify-python-change et
milestone-checkpoint. Rust utilise les contrôles du dépôt, Cargo et rustfmt.

L’audit retrouve `Previews`, `LocalPreviewReader`, `kicad_preview`, le parseur
S-expression, `Drawing`/`Primitive`/`PreviewContent`, les viewers QGraphicsView,
QtPdf et `model_preview`. Les DTO et parseurs KiCad ne dépendent pas de Qt. Qt reste
dans le viewer historique ; le modèle 3D et son interprétation restent hors de
la composition headless TECH-02A. Aucun parseur KiCad n’est réécrit en JavaScript.

## Architecture

```text
UUID composant + rôle (+ UUID asset associé facultatif)
  → Rust : validation et session bornée
  → AssetPreviews : sélection Part/Package, droits d’association/document
  → Previews + port PreviewReader
  → ReadonlyPreviews : copie Asset Store / racine KiCad configurée, SHA-256
  → kicad_preview : Drawing + Primitive
  → JSONL v1 → SVG Svelte

PDF vérifié → snapshot mémoire + handle → blocs de 64 Kio
  → Uint8Array → worker PDF.js local → canvas
```

`AssetPreviews` ne choisit ni n’importe rien. La sélection courante est prioritaire.
Le menu d’aperçu permet de consulter une association différente sans changer le
choix métier. Les documents liés sont également proposés. Sans sélection, un état
explicite invite à consulter un asset associé ; aucun candidat n’est sélectionné
implicitement. Une référence officielle est résolue depuis la configuration de
la copie sans copie vers l’Asset Store, scan ou modification de la bibliothèque.

Les états métier/qualification restent inchangés. Le champ historique
`preview_available: false` dans `get_component` reste inchangé pour compatibilité ;
seule la réponse de preview indique son état effectif, sans valeur de qualification.

## Contrat IPC v1

| Commande | Paramètres contrôlés | Résultat |
| --- | --- | --- |
| `get_asset_preview` | UUID `id`, rôle SYMBOL/FOOTPRINT/DATASHEET/MODEL_3D, `asset_id` UUID facultatif | État explicite, ou provenance/hash/sélection et dessins/handle PDF |
| `read_pdf_chunk` | Handle hexadécimal opaque de 48 caractères, offset multiple de 65536 | Offset, bloc base64 ≤ 64 Kio bruts, marqueur EOF |
| `release_preview` | Handle opaque | Libération idempotente |

Rust refuse les champs inconnus du DTO d’aperçu et les identifiants/offsets invalides.
Une lecture PDF exige un handle retourné par la session courante ; Python vérifie
son existence, sa durée de vie et les bornes. Les commandes de catalogue, leur
sémantique et le protocole v1 sont conservés. Aucune commande de preview n’accepte
un chemin. La WebView ne dispose d’aucune permission filesystem ou shell.

Les dessins transportent nom, unité, variante, unités `mm`, bounds calculés,
primitives avec points/couche/texte/épaisseur/remplissage/rotation/taille et
avertissements. Les bounds tiennent compte des pads tournés et d’une estimation
conservatrice de l’encombrement des textes ; ils ne constituent pas une cotation
mécanique. Les noms de boîtiers ne déterminent jamais la géométrie.

## PDF : choix et limites

Le rendu WebView natif varie selon l’OS. Un moteur indépendant côté Python ajouterait
une dépendance native et des images à transporter. PDF.js **6.4.299**, verrouillé
par npm, offre navigation multipage et canvas locaux sans Qt. Le worker, les CMaps
et polices standard sont embarqués ; aucun CDN, viewer distant ou URL privée.
Un worker explicite évite le repli de PDF.js vers un parsing sur le thread UI avec
l’origine opaque Tauri. Le canvas ne crée aucune couche d’annotations, liens,
formulaires XFA ou scripts PDF. PDF.js 6 a supprimé l’ancien paramètre `isEvalSupported`.

Le document est borné à 16 Mio. Il ne traverse jamais JSONL en une réponse unique :
les blocs de 64 Kio sont assemblés côté frontend, puis le handle est libéré même
si la réponse devient périmée. Deux snapshots Python au plus (32 Mio), handles
aléatoires de 192 bits, expiration à 120 s contrôlée à la prochaine commande,
nettoyage à l’arrêt. Aucun fichier temporaire. Le cache de géométrie est distinct
et ne contient aucun PDF.

Première page, précédent/suivant, compteur, zoom et ajustement de largeur sont
connectés ; « Ouvrir » consulte le document complet dans une vue agrandie. Un PDF
absent, invalide, protégé par mot de passe, trop gros ou en échec de rendu produit
un message explicite. Maximum 2 000 pages, 8 millions de pixels par canvas,
16 millions par image, budgets de lecture/rendu de 10 s de visibilité de la WebView. Le budget est
suspendu lorsque WebKit masque la vue (PDF.js utilise des animation frames).
Une nouvelle page/un nouvel essai efface l’erreur précédente et masque l’ancien
canvas pendant le rendu pour ne pas afficher une page périmée. Les rendus sont annulés
à la navigation ou fermeture et le worker est terminé au démontage.

WASM, ICC, formulaires interactifs, annotations cliquables et saisie de mot de
passe ne sont pas intégrés. La fidélité des PDF complexes/scannés/CJK n’est pas
certifiée par le petit corpus ; l’absence d’une fonction reste un échec explicite
ou une limite du renderer. Pas d’OCR, de recherche textuelle ou de téléchargement.

Référence technique : [API PDF.js](https://mozilla.github.io/pdf.js/api/draft/module-pdfjsLib.html).
Notices Apache, CMaps, Foxit et Liberation conservées et incluses au build.

## Symboles et empreintes

Le parseur existant accepte les versions de symboles datées 20211014–20251024 et
les footprints 20210108–20260206 (plages KiCad 6–10, pas une certification exhaustive).
Il couvre rectangles, cercles, lignes/polylignes, polygones, arcs échantillonnés,
pins et leurs noms/numéros/orientations, unités, variantes et héritage borné.
Les Y des symboles sont inversés côté Python ; les Y PCB restent orientés vers le bas.

Le viewer utilise les formes du DTO, échappe le texte avec Svelte et dessine les
corps avant les pins. Cette dernière règle corrige le recouvrement des noms VCC/GND
du NE555P officiel lorsque des pins d’unité commune précèdent un corps rempli.
Le placement centré des noms longs est corrigé dans le parseur réutilisé.

Pads rectangle/roundrect/cercle/ovale, rotations, numéros, pad 1, perçages centrés
et pad thermique sont représentés. F.Cu, F.SilkS, F.Fab et F.CrtYd sont différenciés
et masquables. Le QFP synthétique montre **48** pads ; le QFN montre **33**, dont
le pad thermique. Couleurs : jetons Fab existants, documentés dans UI_GUIDELINES.
L’identité ambre du logo/liseré et les layouts UX 02 sont conservés.

Zoom 50–800 %, recentrage, agrandissement et sélection unité/variante sont locaux
au viewer. Les petites vignettes de boîtiers denses nécessitent l’agrandissement
pour lire confortablement tous les numéros. Pas de cotations de boîtier inventées,
pas de pan interactif dans ce jalon.

Limites explicites : pads custom/trapézoïdaux, cuivre exclusivement arrière,
perçages décentrés, zones/images et primitives graphiques inconnues sont omis avec
avertissement. Décorations électriques de pins simplifiées. Pins cachées omises
avec avertissement ; conventions historiques de visibilité des labels conservées.
Marquages KiCad de texte (`~{…}`, indices/exposants) affichés littéralement avec
avertissement. Alignement/justification typographique et fontes KiCad ne sont pas
reproduits à l’identique. Les annotations de footprint sont les textes bruts du
fichier (`REF**`, `${REFERENCE}`), sans substitution par une valeur de composant.
Une réussite graphique ne valide ni compatibilité électrique ni fabrication.

Référence : [format S-expression KiCad](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/).

## Sécurité, mémoire et performances

- SQLite reste `mode=ro&immutable=1`, `query_only`, authorizer restrictif. Aucune
  migration, création de table, association, publication ou configuration modifiée.
- Fichiers réguliers uniquement ; containment canonique dans les racines autorisées,
  refus d’échappement via lien symbolique, SHA-256 avant parsing ou réemploi du cache.
  Lecture non bloquante avant fstat pour éviter un FIFO bloquant.
- KiCad : 8 Mio, 100 000 expressions en entrée, profondeur du parseur 128,
  héritage 64, 64 représentations, 5 000 primitives et budget points/textes.
  Le cache LRU contient au plus quatre géométries vérifiées.
- JSONL : requête 16 Kio, réponse 2 Mio, une requête active, timeout Rust 8 s
  (30 s au démarrage). Timeout/rupture ferme la session et écarte les réponses tardives.
- Les requêtes frontend portent une génération logique. Changer de composant ou
  fermer invalide l’ancienne génération, y compris pendant les blocs PDF.
- Le marqueur et les racines configurées protègent contre des erreurs d’usage ;
  ils ne sont pas une sandbox contre un utilisateur local modifiant simultanément
  son propre catalogue/configuration. Aucun log ne contient le contenu des fichiers.
- Le moteur fonctionne avec connexions réseau interdites dans les tests. CSP
  limitée à l’origine locale, IPC et worker local ; aucune ressource distante requise.

## Corpus et non-régression

[Corpus original](../tests/fixtures/previews/README.md), GPL-3.0-or-later : symboles
Simple/FourSides/Multi/Inherited ; DIP8/SOIC8/QFP48/QFN32_EP/R0603/Connector6 ; PDF
original de deux pages. Aucune datasheet fabricant publiée. Les fixtures ne sont
jamais importées par le bundle applicatif.

`tests.preview_corpus` crée exclusivement un nouveau dossier jetable, refusant un
dossier existant. Les cas manquants/corrompus sont produits dans ce catalogue.
Les cas surdimensionnés, FIFO, échappement, expiration et octets périmés sont
créés par les tests. L’option `--official` référence les fichiers KiCad installés,
sans les copier ni les modifier.

## Contrôles automatisés

Commandes depuis le checkout public, avec dépendances installées :

| Contrôle | Commande | Résultat |
| --- | --- | --- |
| Python complet | `QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/pytest -q` | 461 tests |
| Ruff | `.venv/bin/ruff check .` ; `.venv/bin/ruff format --check .` | conformes |
| Typage | `PYTHONPATH=src .venv/bin/mypy` | 152 fichiers, aucune erreur |
| Rust | `cd prototypes/fabparts-tech-01/src-tauri && cargo test --offline` | 11 tests |
| Rustfmt | même dossier, `cargo fmt --check` | conforme, Rust 1.90.0 |
| Frontend TECH | `npm --prefix prototypes/fabparts-tech-01 test` | 21 tests |
| Frontend UX | `npm --prefix prototypes/fabparts-ux test` | 12 tests |
| Svelte | `npm --prefix prototypes/fabparts-tech-01 run check` et équivalent UX | 0 erreur / avertissement |
| Build frontend | `npm --prefix prototypes/fabparts-tech-01 run build` et équivalent UX | réussis |
| Sidecar | `prototypes/fabparts-tech-01/scripts/build-sidecar.sh` | PyInstaller sans Qt |
| Paquet macOS | `npm --prefix prototypes/fabparts-tech-01 run tauri -- build --bundles app --no-sign` | `.app` ARM64 de test |

Les tests couvrent résolutions sélection/association/référence, compte exact des
pads, héritage, DTO, erreurs, intégrité, fichiers hors périmètre, bornes, handles,
absence d’écritures, interdiction Qt/réseau, SVG échappé et ordre de peinture,
zoom, chargement/états, PDF par blocs, annulation et résultats périmés, délai
PDF suspendu hors visibilité et nettoyage du timer.
Les tests IPC existants de timeout, fermeture et transport restent actifs.
Exécuter Cargo après le build frontend : la macro Tauri embarque `dist` et ne doit
pas lire ce dossier pendant son remplacement par Vite.

## Inspection native et captures

Application réelle Tauri, via Computer Use, macOS ARM64 ; aucun navigateur de
simulation utilisé. Tailles logiques : 1440 × 900 puis 1100 × 800 (captures Retina
×2). Thèmes sombre et clair. Polices et icônes embarquées visibles.

| Preuve | Observations |
| --- | --- |
| [Simple + DIP, sombre](tech02a/simple-dip-dark.png) | Deux pins nommées/numérotées, huit pads, contraste, quatre cartes UX 02 |
| [Quatre côtés + SOIC, clair](tech02a/four-sides-soic-light.png) | VCC/GND verticaux, INPUT/RESET/OUT, huit pads |
| [QFP48 agrandi](tech02a/qfp48-dark.png) | 48 numéros réels ; couches F.Cu/F.Fab/SilkS/CrtYd ; masquage/restauration cuivre vérifiés |
| [Unité 2, fenêtre étroite](tech02a/multi-qfp48-narrow-dark.png) | Sélecteur 2/1 actif, fiche stable, pas de débordement horizontal de page |
| [PDF page 2](tech02a/pdf-page-2-light.png) | Navigation 1→2, texte propre au document, compteur 2/2 ; zoom et ajustement testés |
| [PDF absent](tech02a/missing-pdf-light.png) | Ressource introuvable, reste de la fiche utilisable |
| [Fichiers invalides](tech02a/invalid-files-light.png) | Erreur S-expression et PDF, footprint disponible, pas de substitution |
| [NE555P officiel corrigé](tech02a/ne555-official-light.png) | Référence réelle et source KiCad ; pins d’alimentation visibles après correction de superposition |

Zoom du symbole agrandi : 100→150 %, recentrage puis retour à la fiche. Navigation
entre composants pendant les essais sans réponse d’un précédent composant affichée.
L’organisation est celle d’UX 02 : navigation, fiche, colonne de propriétés et grille
2×2 conservées. Aucun statut « prêt » n’est déduit du dessin. Les captures montrent
uniquement le corpus synthétique et les références officielles, jamais la production.

## Packaging, intégrité et dette

Paquet testé : `prototypes/fabparts-tech-01/src-tauri/target/release/bundle/macos/FabParts TECH-01.app`.
Le nom/identifiant TECH-01 sont conservés pour la continuité du prototype ; le pied
de page identifie TECH-02A. Build non signé/non notarié, aucun installateur ou release.
Windows et Linux non exécutés. L’archive PyInstaller ne contient ni PySide6,
shiboken6 ni QtPdf. `health.qt_loaded` observé à false dans l’application.

Les neuf fichiers de production et dix fichiers de la copie TECH-01 sont identiques
aux empreintes de référence privées. La copie synthétique et les deux fichiers
KiCad référencés sont vérifiés avant/après les essais. Aucune donnée métier ou
bibliothèque source modifiée. Les préférences de thème/fenêtre sont uniquement UI.

Dette restante : fidélité typographique KiCad et primitives explicitement non
supportées ; corpus PDF complexe plus vaste ; traduction anglaise complète des
nouveaux contrôles (les commandes de preview ajoutées sont en français) ; pan et
mesures éventuels ; packaging/signature et validation multi-OS. Le bundle principal
Vite dépasse son seuil d’avertissement de 500 Ko à cause du renderer PDF local ;
son chargement peut être séparé lors d’un jalon de performance. Aucun service réseau.

## Critères et arrêt

Critères 1–17 : démontrés sur les formats/corpus supportés et contrôles automatisés.
Critère 18 : inspection native réalisée, captures ci-dessus. Critère 19 : paquet
hôte macOS validé, autres OS explicitement non validés. Critère 20 : respecté,
3D toujours en attente, aucune fonctionnalité TECH-02B/TECH-03.

La branche et la PR sont destinées à la revue Product Owner. Aucun merge de `main`,
force-push ou publication de release. **STOP après ce checkpoint.**
