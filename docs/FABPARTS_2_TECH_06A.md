# TECH-06A — Recherche locale guidée

26 octobre 2026 · `tech/06-guided-discovery` · **GO WITH CONDITIONS**

## Base et périmètre

Les finitions UX ont été poussées dans QUAL-01 (`3fa86fb`) : cadrage SVG visible,
pluriels FR/EN et étude du nommage. PR #8 vérifiée propre, sans conflit ni contrôles
CI publiés, puis fusionnée par merge commit après confirmation directe du Product
Owner : `e3a9108ec480a8427118817e46e24aa1ff4d0a39`. `origin/main` vérifié et branche
TECH-06 créée depuis ce main synchronisé, sans modification locale écrasée.

Cette PR réalise uniquement TECH-06A. Les services M4/M9/M10/M11 et le wizard
ont été examinés ; les fonctions historiques sont réutilisées, sans nouveau
provider ni dépendance.

## Parcours et décisions

À l'étape Identification, **Rechercher des ressources** lance une recherche locale
unique. Les réponses arrivent par rôle dans les quatre cartes : symbole,
empreinte, modèle 3D, datasheet. Les propositions montrent nom, source, nature du
rapprochement, raison vérifiable et package lorsqu'il est connu.

- Catalogue similaire et assets gérés : `Catalogue`, `DocumentationRepository`
  (profils, historique et documents M10) et `LocalResolver`.
- Symboles officiels : `KiCadLibraries` et son index existant.
- Empreinte liée : propriété Footprint, héritage résolu par `LocalResourceProbe`,
  puis concordance des ensembles de numéros pins/pads. Cela reste une proposition
  à qualifier, sans certification de variante ni de géométrie.
- Modèle lié : chemin complet déclaré par l'empreinte, sous
  `${KICAD*_3DMODEL_DIR}`, et référence indexée exactement correspondante. Un
  basename commun dans une autre bibliothèque ne suffit pas.
- Aperçus : services existants de dessins, STEP et PDF ; aucune image de démonstration.

**Examiner n'est pas retenir.** Les aperçus peuvent montrer un premier candidat,
mais les sélections et les champs restent inchangés. Chaque ressource nécessite
« Retenir cette ressource ». Les fichiers fournis restent disponibles ; un choix
existant demeure visible quand une autre proposition est examinée. Le choix d'un
package partagé annonce explicitement qu'il conserve ses ressources partagées.

Les valeurs connues sont proposées champ par champ. Seuls les champs retenus et
confirmés au commit sont enregistrés, avec un lien au Part source et à sa révision
d'identification. Une valeur modifiée manuellement reprend sa provenance de saisie.
Les capacités hors préparation ou incohérentes avec la valeur sont refusées avant
import. Les doublons et la confirmation de variante conservent leurs protections.

Sans résultat/index, un état explicite conserve import manuel et enregistrement
incomplet. La recherche n'écrit ni Part, ni package, ni Asset Store. Les résultats
retardés d'une ancienne identité sont ignorés. Les aperçus reprennent la hauteur
partagée de 144 px et ne doivent pas être relancés par une simple métadonnée.

## Noms exportés : évolution séparée

L'étude détaillée est ajoutée à [QUAL-01](FABPARTS_QUAL_01.md#ux-03--étude-dimpact-du-nommage-mise-en-œuvre-séparée).
M7 exige actuellement un builder unique et reconstruit avec le writer courant.
Un remplacement direct du nommage modifierait donc les octets historiques.

La solution proposée nécessite un dispatcher versionné, un mapping figé des noms
et une base lisible persistante par identité, suffixée de l'UUID complet ; parents
hérités et collisions doivent être contrôlés. Cette évolution est réservée à une
PR dédiée avant implémentation. **M6-1, M7 et les nicknames TECH-05B sont inchangés.**

## Vérifications

- Python complet avec FreeCAD : **605 passed**, dont 12 cas de découverte.
- Ruff et format : conformes, 260 fichiers ; mypy : conforme, 187 modules.
- Rust : **33 passed**, rustfmt conforme.
- Frontend TECH : **86 passed**, Svelte check sans erreur ni avertissement.
- Frontend UX : **12 passed**, Svelte check et build conformes.
- Sidecar et bundle Tauri macOS ARM64 reconstruits et exécutés. Avertissement Vite
  de taille des chunks conservé ; aucune dépendance ajoutée.

Les cas dédiés couvrent variantes synthétiques, héritage, ressource utilisateur
coexistante, résistance générique issue du catalogue, inconnu/index absent,
provenance acceptée/manuelle, capacité falsifiée, changement de contexte,
numérotation incompatible, collision de basename 3D et lecture seule. Une recherche
locale est exercée avec connexion réseau interdite. Les suites existantes couvrent
STALE, ingestion/Asset Store, sauvegarde/restauration, publications, installation,
récupération et rollback. Le nouveau port de liens ne modifie pas Inspection/M5.

## Inspection native et données

Paquet Tauri ARM64 réel, FR sombre en fenêtre normale et EN clair en fenêtre
réduite (environ 901 px de large), défilement et pied d'assistant accessibles.
Données jetables distinctes sous `local-data/tech06a`, copiées depuis QUAL-01 ;
les cinq variables d'environnement FabParts/KiCad ont été vérifiées dans le vrai
processus avant inspection. Aucune application KiCad graphique lancée pour ce jalon.

- NE555D : quatre propositions réelles, symbole SOIC, empreinte huit pads,
  STEP et PDF géré de 39 pages ; aucun champ/choix ajouté automatiquement.
- LM1117MP-3.3 : symbole hérité rendu, empreinte SOT-223/tab 2 et STEP ; absence
  de PDF explicite. Composant existant et métadonnées proposés, sans duplication.
- Résistance générique : Device:R, R_0603_1608Metric et STEP retrouvés depuis le
  catalogue. Sélection du symbole, acceptation de la seule catégorie, puis choix
  explicite du package partagé. Nouveau brouillon de test à nom distinct enregistré ;
  profil relu en SQLite : catégorie seule, source Part/révision conservée, aucune
  datasheet ajoutée. Aucun MPN/fabricant inventé.
- Inconnu : quatre états sans proposition, brouillon enregistré sans ressource.
  Les deux brouillons créés pendant cette passe persistent après redémarrage.
- Retour manuel dans l'assistant : recherche désormais bornée à la référence/MPN,
  plutôt qu'à une requête vide susceptible d'afficher un PDF sans rapport.
- Acceptation d'une métadonnée : compteur des requêtes d'aperçu inchangé (trois
  avant/après pour la résistance) ; aucune conversion relancée.

La copie figée du résultat (cinq Parts) est lue par le sidecar embarqué ; découverte
et commit sont refusés READ_ONLY, inventaire inchangé. Sauvegarde complète créée
et vérifiée sur ces données, avec les nouveaux historiques d'identification.
Les neuf inventaires protégés sont identiques au début : préférences personnelles
KiCad, données KiPart Manager, absence du workspace personnel FabParts, trois
corpus TECH-05B et données/configurations/sources QUAL-01. Les publications
historiques et installations de référence restent donc inchangées.

Captures : [LM1117, EN clair, fenêtre réduite](tech06a/guided-lm1117-en-light.jpg),
[STEP/PDF NE555D non retenus, FR sombre](tech06a/guided-ne555-step-pdf-fr-dark.jpg),
[brouillon de résistance enregistré](tech06a/saved-resistor-fr-dark.jpg).

## Limites et suite proposée

La recherche est textuelle et bornée : dix composants similaires, quarante
propositions par rôle ; exploration des liens des quatre premiers symboles et huit
premières empreintes. Pas de déduction de fabricant depuis un nom de symbole,
pas d'identité commerciale inventée pour une résistance générique, pas de recherche
sémantique. Sans profil local, les métadonnées restent manuelles. Un nouveau package
sans équivalent dans le catalogue reste à nommer explicitement. Les chemins 3D non
reconnus ne sont pas devinés. La configuration/reconstruction de l'index utilise
les outils locaux existants ; aucun écran de configuration d'index ajouté ici.

TECH-06B proposé : raccorder `RemoteLibraries` M9 et `Documentation` M10 aux actions
explicites de recherche/téléchargement/import, avec provenance et conservation des
sources locales. Pas de connexion au démarrage. SnapMagic reste désactivé tant que
son contrat API réel n'est pas disponible. TECH-06C utilisera `Assistance` M11
séparément, après revue, consentement par envoi et acceptation champ par champ.

Aucune partie B/C n'est implémentée ni activée dans cette PR.

## Décision

**GO WITH CONDITIONS** : recherche locale guidée et décisions explicites vérifiées,
aucun défaut bloquant connu dans les parcours testés. Les réserves sont les limites
bornées ci-dessus et le nommage versionné réservé à une PR dédiée. Cette passe
ne requalifie pas d'autres plateformes ni d'autres versions KiCad ; les protections
de publication/installation sont vérifiées par les suites existantes et la
préservation des inventaires, sans nouvelle activation globale native.

Commit et PR vers main ; ne pas fusionner TECH-06A automatiquement. **STOP**.
