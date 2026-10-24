# Identité KiPart Manager

Logo approuvé fourni par l’utilisateur : **QFP Balanced — Optical Balance**, intégré
le 16 octobre 2026. Les trois SVG ont été déplacés de `logo/` vers le package,
sans modification d’un seul octet. Ils constituent les seules sources canoniques.
Les aperçus initiaux restés dans `logo/` sont des références historiques, pas des
sources à exporter. Aucun logo FabCAM n’a été modifié.

## Ressources embarquées

```text
src/kipartmanager/ui/
├── branding.py
└── branding/
    ├── source/
    │   ├── symbol.svg                 # symbole transparent
    │   ├── app_icon.svg               # icône carrée graphite approuvée
    │   └── lockup_kipart_manager.svg   # signature horizontale fournie
    └── app/
        ├── kipart-icon.icns
        ├── kipart-icon.ico
        └── png/kipart-{16,24,32,48,64,128,256,512,1024}.png
```

Le SVG d’application reste dans `source/` ; aucune copie concurrente dans `app/`.
Les PNG/ICO/ICNS sont des dérivés. Branding et Asset Store électronique sont distincts.
Le lockup reste inchangé, avec son texte SVG et sa pile de polices Inter / Noto Sans /
sans-serif : la police disponible peut influencer son rendu. Aucun wordmark inventé.

| Source | SHA-256 à réception |
| --- | --- |
| symbol.svg | `f9338fce7b32a705f17381e9680de0f1bc6556595717881ff2d80ade665cf06c` |
| app_icon.svg | `46e0d3e144965c1ac6505b07c69708f8acbb22b164a20c5390e5876cd89ff483` |
| lockup_kipart_manager.svg | `df83511120a81f52d69f4c7b8652fd6375c22c9add112e0bb3162dba40eace30` |

Couleurs originales : graphite `#171E28`, cadre `#354250`, ambre `#E8B954`,
repère pin 1 `#F5F1E8`, texte du lockup `#EEF3F8`. Le logo conserve exactement son
cadre arrondi, ses 12 pads (trois par côté), son boîtier et son repère blanc.

La suite partage un langage graphite et géométrique : FabCAM bleu, KiPart Manager
ambre, FabSBP rouge envisagé. L’ambre porte aussi les accents interactifs de KiPart
depuis la passe d’alignement du thème : sélection, focus et actions principales.
Les couleurs sémantiques restent indépendantes. La palette et ses états sont
formalisés dans [UI_GUIDELINES.md](UI_GUIDELINES.md).

## Régénérer

Depuis un checkout ou un sdist extrait, avec les dépendances Python de l’application :

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/export_branding.py
```

Le script résout ses chemins relativement à lui-même. Il utilise Qt SVG, QImage et
la bibliothèque standard, sans dépendance ajoutée ni outil de dessin externe.
Rendu direct depuis `app_icon.svg` à chaque résolution, transparence et antialiasing
conservés. ICO multi-résolutions PNG (16 à 256, Windows Vista+) ; ICNS avec slots
standard PNG 16 à 1024 et variantes Retina. Les SVG ne sont jamais réécrits.
Une évolution de Qt peut modifier l’antialiasing : comparer visuellement les dérivés.

## Intégration et distribution

`ui/branding.py` charge l’icône SVG via le chemin du module installé, indépendamment
du répertoire courant. Bootstrap définit `QApplication.windowIcon` et le nom desktop
`kipartmanager`. MainWindow définit aussi son icône pour les compositions directes.
La sidebar utilise le même QIcon à 32 px, à côté du nom ambre ; sa largeur est
conservée. Aucun About, splash ou accueil dédié n’existe ; aucun écran n’a été ajouté.

Le packaging existant est **setuptools : wheel + sdist**, avec point d’entrée console.
`pyproject.toml` embarque les trois SVG et tous les dérivés ; `MANIFEST.in` ajoute le
script de régénération au sdist. Aucun pipeline PyInstaller, bundle `.app`, installateur
Windows, paquet Linux ni lanceur `.desktop` n’existe actuellement dans ce dépôt.
Il n’a pas été créé de nouvelle chaîne de distribution pour cette tâche.

Lors de l’introduction d’un tel packaging, utiliser les ressources déjà préparées :

- macOS : copier `kipart-icon.icns` dans `Contents/Resources` et référencer son nom
  via `CFBundleIconFile` dans Info.plist ; vérifier Finder, Dock et Cmd-Tab sur le bundle.
- Windows : utiliser `kipart-icon.ico` pour l’icône de l’exécutable et des raccourcis
  de l’installateur ; vérifier ensuite barre des tâches et raccourcis sur Windows.
- Linux : installer le SVG d’application ou les PNG dans le thème hicolor sous le nom
  `kipartmanager`, et utiliser `Icon=kipartmanager` dans `kipartmanager.desktop`.

Ces réglages sont des points d’intégration futurs, pas une configuration desktop déjà
présente. QIcon à l’exécution ne remplace pas les métadonnées d’un bundle distribué.

## Vérification du checkpoint

- 387 tests réussis ; Ruff check/format et mypy strict réussis (138 fichiers avec script).
- Tests de conservation SHA des sources, dimensions/décodage PNG, répertoires ICO,
  contenu/longueurs/slots ICNS, chargement SVG/QIcon et lancement Qt depuis un autre cwd.
- Build wheel + sdist réussi ; wheel installée sans dépendances dans un dossier
  temporaire, application réellement lancée depuis `/tmp`, ressources prises dans
  cette installation, icônes application/fenêtre et sidebar vérifiées.
- Contrôle natif macOS, vues vides/remplies, tailles 1200×800, 900×680 et 1600×950
  demandées (hauteur limitée par l’écran). Inspection de la sidebar et des petites tailles.
- ICNS lu et extrait avec l’outil Apple `iconutil` ; ICO décodé par Qt sur macOS.
- Pas de validation native Windows/Linux ni de validation Finder/Dock/Cmd-Tab d’un
  `.app` autonome : aucun bundle desktop existant à tester.

À 16 px, pads et repère sont soumis à une forte réduction : le diamètre du repère
est de 0,56 px. La forme reste identifiable mais les détails sont peu distincts.
À 24/32 px ils deviennent plus lisibles. Aucun épaississement, déplacement ou dessin
spécial petites tailles n’a été introduit, afin de préserver la géométrie approuvée.
