# Aperçus locaux — UX A1 / A2

Les aperçus servent à inspecter une ressource, sans l’importer, la choisir ou la
qualifier. Ils sont disponibles depuis Fichiers & ressources, les ressources
choisies de la fiche composant, KiCad local, les candidats locaux du résolveur et
Datasheets & documents. Le bouton reste désactivé sans sélection compatible.

## Symboles

Le viewer dessine contours, lignes, cercles, arcs, polylignes et broches, avec noms
et numéros disponibles. Les noms/numéros sont affichés pour l’inspection même
lorsque KiCad masque leurs libellés ; les broches elles-mêmes cachées ne sont pas
tracées et leur absence est signalée. Les noms `~` ne fournissent pas de libellé.
Le sélecteur distingue entrée, unité et représentation, et inclut les formes
communes et l’héritage local de l’entrée. Il ne superpose pas plusieurs unités.

## Footprints

Vue de dessus : pads dorés, pad 1 rouge, sérigraphie bleue, fabrication grise et
courtyard violet en pointillés. Numéros des pads et perçages centrés sont visibles.
Les pads rectangulaires, circulaires, ovales et arrondis prennent en compte leur
rotation. Les références/valeurs et autres textes sont affichables à la demande
pour ne pas masquer la géométrie. Zoom, déplacement par glisser et recentrage sont
communs aux deux viewers KiCad.

Les textes utilisent la police Qt : ce n’est pas un rendu identique à l’éditeur
KiCad. Les décorations électriques complexes des broches sont simplifiées.
Les pads custom/trapézoïdaux, courbes Bézier, zones et autres éléments non pris en
charge sont signalés comme un aperçu incomplet. Les perçages décentrés ne sont pas
dessinés et sont signalés. Un fichier malformé ou d’une version non reconnue est
refusé avec un message. La validation métier M5 reste indépendante du viewer.

## PDF

QtPdf/QtPdfWidgets, inclus dans PySide6, affichent toutes les pages du document
local. Le sélecteur de page, le défilement, le zoom, le recentrage et
l’agrandissement de la fenêtre permettent de consulter le document complet.
Provenance, source et SHA-256 sont accessibles dans un détail repliable.
Les documents illisibles/protégés/non supportés produisent un message explicite.
La restitution d’une copie reste disponible dans Documentation et Fichiers.
Aucun téléchargement, extraction de texte ou référence de page IA n’est ajouté.

## Architecture et intégrité

`Previews` est un service applicatif utilisant le port `PreviewReader`.
`LocalPreviewReader` lit des snapshots bornés et compare leur SHA-256 à l’identité
persistée. Les fichiers gérés vérifient également leur taille ; les références
KiCad doivent rester dans la racine configurée. Aucun fichier source n’est écrit.
Une fenêtre déjà ouverte présente le snapshot vérifié à son ouverture : elle ne
constitue pas un contrôle continu des changements du fichier.

Le parsing des formats est dans l’infrastructure, les primitives de dessin sont
sans Qt, et le rendu est dans l’UI. Le domaine et la base ne changent pas.
Lecture limitée à 64 Mio pour KiCad et 128 Mio pour les PDF ; les représentations
et éléments graphiques sont également bornés. Aucun nouveau package requis.

La lecture suit les conventions officielles :
[S-expressions KiCad](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/).

## Périmètre suivant

A2 est livrée avec la couverture décrite ci-dessous. B : amélioration du parcours et
comparaison structurée. C/D : intégration progressive des métadonnées et de
l’assistance existantes. A1 ne développe aucun générateur ni nouvelle fonction IA.

## A2 — Modèles 3D WRL / STEP

Les accès « Inspecter » sont désormais disponibles pour les modèles choisis de la
fiche composant, les fichiers gérés, KiCad local et les candidats locaux du résolveur.
L’aperçu est non modal et indépendant du choix, de l’import et de la qualification.

- Glisser avec le bouton gauche : rotation ; bouton droit : déplacement.
- Molette ou boutons −/+ : zoom borné ; Recentrer : cadrage initial.
- Vues Isométrique / Dessus / Face / Droite, dans le repère propre au fichier.
- Provenance, source et SHA-256 du snapshot inspecté restent consultables.

Le viewer n’assemble pas le modèle au footprint et n’applique pas de placement,
offset ou rotation provenant d’un footprint. Il ne mesure pas les dimensions et
ne fournit aucune validation de correspondance mécanique.

### WRL sans logiciel supplémentaire

Lecture locale d’un sous-ensemble **VRML97 / V2.0 UTF-8** : Group, Transform
(translation, rotation, center, scale et scaleOrientation), Shape, IndexedFaceSet,
Coordinate, matériaux diffus et références DEF/USE déjà définies.
Les faces convexes sont conservées ; la profondeur est calculée par pixel.

VRML 1, primitives Box/Sphere/etc., faces déclarées non convexes, échelles nulles
ou négatives, nœuds inconnus et scènes dynamiques sont refusés explicitement.
Inline, Script, PROTO, EXTERNPROTO et ROUTE sont refusés ; aucun script, URL,
texture ou fichier externe n’est chargé. Textures, transparence et couleurs par
sommet/face sont simplifiées avec un avertissement. Normales, éclairages et
spécularité du fichier ne sont pas reproduits : éclairage diffus d’inspection.

Le parsing suit la [référence VRML97 de Web3D](https://www.web3d.org/documents/specifications/14772/V2.0/part1/nodesRef.html),
notamment IndexedFaceSet et l’ordre des transformations. Ce n’est pas un navigateur
VRML généraliste. Il n’y avait pas de WRL dans les modèles de l’installation KiCad
locale utilisée pour le contrôle : les tests WRL utilisent des fixtures déterministes.

### STEP : moteur FreeCAD local facultatif

STEP nécessite un noyau CAO pour tesseller ses surfaces. Le choix retenu est
FreeCAD en sous-processus local, sans l’importer dans l’interpréteur de KiPart et
sans ajouter de dépendance Python lourde. API de lecture et tessellation :
[FreeCAD Part / TopoShape](https://freecad.github.io/SourceDoc/d8/ded/classPart_1_1TopoShape.html).

Détection au moment de l’inspection uniquement : `freecadcmd` ou `FreeCADCmd`
dans PATH ; sur macOS, installation standard `FreeCAD.app` dans `/Applications`
ou `~/Applications`. Pour une autre installation, définir `KIPART_FREECAD_CMD`
vers l’exécutable console de FreeCAD, pas vers son lanceur GUI. Un chemin explicite
invalide produit un échec explicite, sans substitution par un autre logiciel.

Exemple de lancement Linux avec une installation locale :

```sh
KIPART_FREECAD_CMD=/opt/freecad/bin/freecadcmd kipartmanager
```

L’application n’installe et ne télécharge rien. FreeCAD absent, indisponible ou
incapable de lire le fichier : message récupérable dans l’aperçu ; le reste de
l’application et les autres viewers restent utilisables.

Le snapshot contrôlé est copié dans un dossier temporaire privé. FreeCAD reçoit
ce snapshot et un script fixe de lecture/tessellation, jamais le chemin du fichier
canonique. Ses fichiers de configuration sont également dirigés vers ce dossier.
Les variables Qt/Python héritées sont isolées pour éviter de charger les bibliothèques
du processus KiPart dans FreeCAD. Le dossier est supprimé après succès ou échec.

Tessellation STEP à 0,15 mm ; rendu monochrome, sans conservation des matériaux
ou des noms de pièces. Maillage intermédiaire éphémère : aucun nouvel Asset n’est
créé, aucun fichier source n’est réécrit. Conversion interrompue après 30 secondes.

### Rendu, limites et chargement

Projection orthographique, rendu logiciel avec tampon de profondeur, indépendant
d’OpenGL et sans dépendance ajoutée. Image mise en cache, jusqu’à 1280 pixels sur
le grand côté au repos, 480 pendant un glisser ; le zoom permet de voir les détails
à la résolution du viewport. La fluidité dépend du modèle et du processeur ; les
modèles très complexes peuvent demander un viewer CAO spécialisé.

Limites : entrée 64 Mio comme A1 ; 600 000 tokens WRL, imbrication 48 ; 60 000
sommets, 20 000 faces, 256 sommets par face ; sortie STEP JSON de 16 Mio. Valeurs
finies, indices, dimensions des listes et couleurs contrôlés avant rendu.
Les modèles dépassant ces limites sont refusés, sans aperçu tronqué silencieux.

La lecture et la conversion 3D s’exécutent dans un worker. La fenêtre reste active ;
sa fermeture, Échap et la fermeture de son parent attendent la fin du worker pour
éviter de détruire un thread en cours. Aucun bouton d’annulation de conversion
n’est ajouté ; la limite STEP est de 30 secondes. Les erreurs gardent un état vide
stable et désactivent les contrôles de vue et les détails d’un aperçu non établi.

A2 ne modifie ni SQLite, ni l’Asset Store, ni les choix de ressources, ni les
publications. Comparaison structurée B et génération M12+ restent hors périmètre.
