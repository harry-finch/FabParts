# FabParts 2.0 — TECH-02B

## Préparation et checkpoint architectural

Base : `main` synchronisé au merge TECH-02A `2d24fea`, correctif PDF `4e2026e`
inclus ; checkout propre. Branche `tech/02b-real-3d-previews`. Archive privée et
catalogues de production conservés.

Audit : `model_preview.py` contient un parseur VRML97 borné (Group/Transform,
IndexedFaceSet, DEF/USE, matériaux diffus) et un adaptateur FreeCAD externe. Le
port `Mesh` et la résolution Part/Package/asset sont réutilisables sans Qt. Le
viewer historique `ModelView` est un rasteriseur logiciel PySide6, non réutilisé
par la WebView. La triangulation historique en éventail présuppose la convexité :
elle doit être contrôlée, jamais appliquée silencieusement à une face concave.
Les textures, scripts et ressources externes ne seront pas chargés.

FreeCAD 1.1.1 (révision 20260414) est installé sur le poste macOS ARM64 ; son
exécutable console répond hors du bac à sable (la détection NEON de Qt échoue dans
ce dernier). L’installation occupe environ 2,6 Go. Elle reste **externe et
facultative**, sans ajout de Qt dans le sidecar et sans téléchargement automatique.

| Choix | Évaluation |
| --- | --- |
| Three.js + OrbitControls, intégration Svelte légère | Retenu : WebGL, géométrie neutre, caméra et nettoyage explicites, licence MIT |
| Renderer WebGL sur mesure | Écarté : maintenance des contrôles/matériaux et compatibilité disproportionnée |
| Wrapper Svelte de scène | Inutile pour un seul mesh/viewport ; dépendance supplémentaire |
| glTF/GLB intermédiaire | Inutile pour ce DTO de triangles/couleurs ; ajouterait exporteur/importeur et sémantique de scène |
| FreeCAD externe | Retenu : réutilisation de la lecture STEP/tessellation existante, pas d’alourdissement du paquet |
| OCCT/FreeCAD embarqué | Non retenu sans décision PO : dépendance native, taille et packaging multi-OS majeurs |

Sources : [OrbitControls](https://threejs.org/docs/pages/OrbitControls.html),
[nettoyage Three.js](https://threejs.org/manual/pages/how-to-dispose-of-objects.html),
[licence MIT](https://github.com/mrdoob/three.js/blob/dev/LICENSE),
[FreeCAD headless](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Headless_FreeCAD.md).

Décision : poursuivre sans nouvelle infrastructure CAO. Un worker 3D local borné
traite le snapshot contrôlé, sans accès SQLite. Les commandes de démarrage/statut,
lecture par blocs et libération restent courtes et additives à JSONL v1. Le timeout
catalogue de 8 s reste inchangé. Annulation, expiration et arrêt libèrent le résultat
et terminent FreeCAD. Les principes de snapshots PDF sont réutilisés pour le transport.
Le renderer reçoit uniquement un maillage triangulé validé et des métadonnées bornées.

WRL : coordonnées du fichier conservées ; aucune multiplication universelle par
2,54. La convention KiCad historique est de 0,1 pouce par unité WRL, mais un fichier
VRML générique ne prouve pas cette convention. Le viewer ne certifie pas de mesure
physique ni de placement footprint. STEP : coordonnées normalisées en mm par FreeCAD.
Référence : [convention KiCad](https://dev-docs.kicad.org/en/file-formats/legacy-pcb/index.html).

## Architecture et contrats finaux

Résolution `Part → Package → sélection/association MODEL_3D` dans `AssetPreviews`,
lecture readonly et SHA-256 dans `ReadonlyPreviews`, snapshot immuable en mémoire,
`ModelJobs(MeshConverter)` puis parseur WRL/FreeCAD et triangulation contrôlée.
Le worker n'accède ni à SQLite ni aux services métier. Pas de modification des
parseurs KiCad, du stockage, des qualifications ou des quatre cartes.

| Commande v1 | Contrat |
| --- | --- |
| `get_asset_preview` avec rôle `MODEL_3D` | UUID métier/asset associé ; retourne provenance et `{status: loading, handle}` |
| `get_model_status` | Handle de cette session ; loading, ready ou erreur structurée |
| `read_mesh_chunk` | Handle et offset multiple de 65 536, inférieur à 16 Mio ; base64, offset, eof |
| `release_model_preview` | Annule/libère idempotemment ; Rust supprime exactement le handle après `released: true` |

FPM1 : 12 octets d'en-tête (magic, nombres de sommets/triangles u32 little endian),
positions xyz f64, indices triangulés u32, RGB f32 par triangle, puis un octet de
sidedness par triangle. Longueur exacte `12 + 24V + 25T`. Les métadonnées contiennent
format, bounds, unités, warnings, taille, taille de bloc et SHA-256 du mesh. Aucun
JSON massif de coordonnées. Rust contrôle le descripteur ; le frontend contrôle
longueur exacte, nombres, indices, valeurs finies, couleurs, flags et empreinte
avant allocation GPU. Les positions sont recentrées en f64 avant passage en f32.

## WRL et fidélité

Réutilisation du sous-ensemble VRML97 existant : IndexedFaceSet, Group, Transform,
DEF/USE, translation/rotation/échelle positive, centre et scaleOrientation. `ccw FALSE`
inverse les indices ; `solid FALSE` seul justifie le matériau double face.
Les polygones doivent être plans, convexes, non dégénérés et sans indices répétés.
Le contrôle de demi-plans rejette aussi les étoiles auto-intersectées ; aucune
triangulation aveugle des faces concaves. Les sommets collinéaires de bord peuvent
être retirés de la triangulation sans suppression de surface.

Les normales sont recalculées par triangle ; couleurs diffuses préservées. Matériau
absent, transparence, lissage, textures ou couleurs par sommet non reproduits sont
signalés selon les capacités du parseur existant. Scripts/Inline et nœuds non pris
en charge sont rejetés ; aucune texture ou URL n'est ouverte. Les contrôles et
limites du parseur restent actifs, avec annulation ajoutée pendant parsing/visite.
Une géométrie valide reste un aperçu, jamais une certification mécanique.

## STEP et dépendance externe

Le chemin FreeCAD peut être trouvé dans PATH, dans l'installation macOS usuelle,
ou choisi par l'utilisateur au lancement via `KIPART_FREECAD_CMD`. Rust transmet
uniquement cet override explicite au sidecar ; la WebView ne peut pas le définir.
Le sidecar conserve son environnement nettoyé et l'installation standard macOS est
le chemin réellement qualifié. Sous Windows/Linux, prévoir l'override explicite ;
ces plateformes n'ont pas été exécutées pendant ce checkpoint.

FreeCAD lit une copie temporaire, tesselle à 0,15 mm et retourne vertices/triangles.
Les volumes disjoints sont conservés ; les matériaux STEP sont simplifiés en teinte
neutre, sans prétendre préserver les couleurs constructeur. Aucun FreeCAD/OpenCascade
n'est redistribué. Un convertisseur absent produit `converter_missing`, sans
chargement automatique. Le binaire externe conserve ses propres dépendances Qt ;
le sidecar FabParts n'importe ni ne bundle PySide6/Qt.

| Fixture STEP originale | Sommets / triangles | Mesh FPM1 | Temps observé |
| --- | --- | --- | --- |
| box.step, 10×6×2 mm décentré | 8 / 12 | 504 octets | 0,327 s |
| package.step, corps + 8 pins | 72 / 108 | 4 440 octets | 0,169 s |
| details.step, plaque percée | 1 016 / 2 044 | 75 496 octets | 0,180 s |

Mesures locales ponctuelles Python + FreeCAD 1.1.1 sur macOS ARM64, non benchmark
universel. Bounds WRL/STEP comparés pour box et package, identiques dans ce corpus
déclaré en mm. Sources originales GPL-3.0-or-later, générateurs et attentes dans
[le corpus](../tests/fixtures/models/README.md). Aucun modèle fabricant ajouté.

## Conversions longues, sécurité et ressources

Un worker, deux jobs/snapshots 3D, deux snapshots PDF indépendants. TTL 120 s,
libération après transfert, lors de la navigation, de l'expiration ou de l'arrêt.
Un troisième job annule le plus ancien. Un job annulé encore en cours peut retenir
son snapshot jusqu'au prochain contrôle d'annulation ; donc au plus trois sources
3D de 16 Mio pendant ce bref chevauchement. Deux résultats de 16 Mio maximum ; le
format actuel et ses limites géométriques limitent en pratique chaque FPM1 à moins
de 3 Mio. Le frontend conserve le mesh courant, sans cache de navigation.

Fichier 3D 16 Mio ; 60 000 sommets, 20 000 faces source, 60 000 triangles ; WRL
600 000 tokens, profondeur 48, face 256 indices, 100 000 visites. Budget de contrôle
polygonal : somme des carrés des tailles de faces ≤ 2 millions. Requête/réponse
JSONL restent bornées, réponse ≤ 2 Mio, blocs base64 < 90 Ko. Un test transporte
un mesh de 2 190 012 octets, supérieur à la trame JSONL, sans dépasser celle-ci.

FreeCAD : délai mural 30 s, contrôle d'annulation toutes les 50 ms ; terminate puis
kill si nécessaire, nettoyage TemporaryDirectory. Logs dirigés vers DEVNULL pour
éviter leur croissance. CPU/fichier de sortie bornés sur POSIX ; limite d'espace
virtuel de 2 Gio ajoutée sur Linux. **Pas de plafond RSS portable garanti sur macOS
ou Windows** : les limites mémoire Darwin ont été rejetées lors de la qualification,
elles ne sont pas présentées comme une protection effective. L'entrée, la sortie,
la concurrence et la durée restent bornées. Le coût mémoire interne d'OCCT avant
contrôle du mesh demeure une réserve pour des STEP hostiles/complexes.

Le convertisseur hérite du groupe de processus/job du sidecar : l'arrêt forcé
Rust inclut les descendants. Le shutdown coopératif annule d'abord les jobs.
Les handles sont opaques, séparés PDF/3D, liés à la session ; restart remplace tous
les registres. Aucun droit général shell/filesystem dans les capabilities WebView.

## Viewer et cycle GPU

Three.js 0.186.1 + OrbitControls, MIT. Géométrie triangulée et normales calculées
une fois par montage, au plus deux groupes de matériaux. Perspective 35°, caméra
Z-up, centrage selon la bbox et cadrage selon rayon/aspect. Vues iso/dessus/dessous/
face/arrière, rotation souris, zoom molette ou boutons, pan droit/Maj ou bouton main,
recentrage. ResizeObserver adapte le viewport. Les miniatures et le dialogue
n'affichent pas deux viewers 3D simultanés pour la même carte.

Un seul requestAnimationFrame en attente, rendu uniquement sur invalidation ; pas
de boucle d'animation persistante. Intersection/visibilité suspendent les dessins,
DPR limité à 2. Au démontage : observers/listeners/contrôles, géométrie, matériaux,
renderer et contexte libérés. Perte de contexte signalée ; restauration réactive
le rendu. WebGL indisponible affiche une erreur explicite. Les contrôles sont FR/EN.
L'éclairage a été réduit après inspection du thème clair pour mieux lire les volumes.

## Vérifications automatisées

- Suite Python complète avec `FABPARTS_TEST_FREECAD=1 PYTHONPATH=src .venv/bin/pytest -q` :
  478 tests réussis en 54,53 s, dont les trois conversions STEP réelles et le
  transfert d’un mesh supérieur à 2 Mio.
- Ruff sur src/tests/générateurs : réussi ; mypy strict : 157 fichiers sans erreur.
- Rust 1.90, tests offline : 20 réussis ; rustfmt : réussi. Handles hors ordre,
  registres séparés, refus après restart, métadonnées invalides, fermeture et
  non-régression PDF H1/H2/H3 couverts.
- Frontend TECH : 28 tests réussis, incluant vrais OrbitControls (rotation, zoom,
  pan), cadrage, vues, perte/restauration de contexte, destruction et échec WebGL.
- Frontend UX : 12 tests réussis. Svelte check des deux frontends : zéro erreur,
  zéro avertissement. Les deux builds passent.
- Diff final inspecté : aucun binaire applicatif, environnement local ou catalogue
  suivi. `git diff --check` est propre hors des quatre espaces finaux natifs des
  exports STEP originaux, conservés pour garder les fixtures testées inchangées.
- Un test TECH-02A supposait l'ordre des asset_ids/UUID ; corrigé pour retrouver
  explicitement la sélection SYMBOL, sans masquer un échec de production.

## Inspection native

Application Tauri macOS réelle, corpus synthétique uniquement. Fenêtre 1440×900
puis 1100×800, thèmes sombre et clair. WRL simple, WRL à neuf formes/deux matériaux,
STEP simple et multi-solides réellement convertis ; rotation, zoom molette, pan,
recentrage et les cinq vues contrôlés. Sélection d'une ressource associée sans
modification métier ; retours/changements de fiches sans apparition de résultat
périmé. Ressource manquante, WRL invalide et STEP invalide donnent des erreurs
explicites. Symboles, empreintes et PDF restent visibles/consultables.

Une copie locale du même exécutable, avec identifiant de bundle distinct et
`LSEnvironment` de test, a servi à simuler FreeCAD absent puis un processus lent de
25 s. Aucun changement de FreeCAD installé. Le message d'absence est vérifié dans
la véritable WebView. Retour au catalogue pendant conversion après > 8 s : neuf
résultats accessibles ; processus annulé et dossier temporaire supprimés. Deuxième
conversion : fermeture par menu Quit pendant activité ; aucun sidecar/convertisseur
restant, dossier supprimé. Ce harnais n'est ni distribué ni ajouté au dépôt.

Captures natives, données originales uniquement :

- [WRL simple, quatre cartes](tech02b/wrl-box-dark.png)
- [WRL multi-formes](tech02b/wrl-package-dark.png)
- [STEP simple](tech02b/step-box-dark.png)
- [STEP multi-solides clair](tech02b/step-package-light.png)
- [Fenêtre étroite](tech02b/step-package-narrow.png)
- [STEP avec détails fins et perçages](tech02b/step-details-light.png)
- [WRL invalide, PDF préservé](tech02b/invalid-wrl-light.png)
- [Convertisseur absent](tech02b/converter-missing.png)

## Packaging et intégrité

Sidecar PyInstaller reconstruit ; bundle Tauri ARM64 `.app` construit avec
`--no-sign`, 27,33 Mio. Pas de signature/notarisation ni release. FreeCAD reste une
installation externe d'environ 2,6 Go, non comprise dans cette taille. Vite émet
l'avertissement de chunk > 500 Ko (bundle local incluant PDF.js/Three.js) ; ce n'est
pas une erreur de build. Les licences exactes Three/PDF.js/Inter/Lucide sont copiées
dans dist ; inventaire npm et notices mis à jour.

SHA-256 inchangés : production (9 fichiers), copie TECH-01 (10), corpus TECH-02A
(13), corpus TECH-02B (20) et fixtures 3D (9, README compris). Aucune écriture métier,
association, import, publication ou changement de fichier source pendant les
aperçus. Les seuls ajouts de catalogue ont lieu à la création d'un nouveau corpus
jetable, avant la référence d'intégrité. Les archives privées restent exclues.

## Réserves et décision

**GO WITH CONDITIONS** pour revue Product Owner : fonctions principales connectées
et qualifiées sur macOS ARM64 avec FreeCAD 1.1.1. Réserves : pas de qualification
Windows/Linux, pas de distribution signée, pas de plafond RSS FreeCAD portable,
sous-ensemble VRML convexe statique, matériaux STEP simplifiés, tessellation 0,15 mm
non adaptée à une mesure certifiée. Les gros modèles sont refusés par les limites,
pas simplifiés silencieusement. Une validation fournisseur exhaustive reste hors
de ce corpus original. WebGL indisponibilité/perte de contexte sont testées avec
renderer de test ; panne GPU matérielle non provoquée sur le poste.

Aucune fusion, release ou fonctionnalité TECH-03. STOP après ouverture de la PR.
