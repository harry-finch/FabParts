# TECH-05B — Global KiCad Integration

26 octobre 2026 · `tech/05b-global-kicad-integration` · **GO WITH CONDITIONS**

## Base et périmètre

PR #6 TECH-05A vérifiée sans conflit, sans contrôles CI publiés, puis fusionnée
avec un merge commit : `a3d3985d212daa23a917a33dd0115b31f5fe52d0`.
Branche créée depuis ce nouveau main dans le checkout officiel
`harry-finch/FabParts`. Aucun historique de l'ancien checkout reconstruit.
Aucune fonction TECH-06, synchronisation automatique ou édition de projet ajoutée.

## Architecture et données

`KiCadIntegration` utilise un port dédié ; `LocalKiCadIntegration` réutilise la
reconstruction M6/M7 depuis une publication engagée et vérifiée. Le catalogue
courant n'intervient pas dans l'activation historique. Domaine, schéma SQLite,
format M7 et moteur de publication restent inchangés.

Une copie neuve sous `config/kicad-integration/installed/<collection>/<version>/<id>`
remplace les références `${KIPRJMOD}` par ses chemins absolus contrôlés. Le nickname
`FabParts_<UUID de collection sans tirets>` reste stable entre versions et renommages.
Tables internes, références d'empreintes, modèles 3D et datasheets sont vérifiés.
Inventaire SHA-256, manifeste d'installation et sceau READY protègent les copies.
Une réactivation réutilise une copie intacte ; une copie altérée est conservée,
jamais écrasée. Les dossiers M7 historiques et les bibliothèques officielles ne
sont pas des destinations d'installation. Les chemins absolus sont propres à cette
installation locale ; les publications historiques gardent leurs chemins portables.

Rust détecte les applications KiCad macOS, leur version et la racine de configuration
native ou son override hôte. La WebView transmet uniquement UUID, cible, numéro de
publication et capacité éphémère liée au résumé. Aucun chemin, manifest ou shell
arbitraire n'est accepté. Rust et Python refusent les écritures en readonly,
pendant une préparation ou après restauration avant redémarrage. Rust recontrôle
la présence du gestionnaire/éditeurs KiCad avant les mutations. Une sonde de version
utilise maintenant une configuration et un répertoire de documents temporaires isolés.

## Tables, sauvegarde et reprise

L'éditeur par positions conserve les octets des entrées tierces, leur ordre,
options, descriptions et espaces. Il insère seulement une entrée FabParts ou change
l'URI de l'entrée dont les champs correspondent à son état précédemment enregistré.
Un nickname préexistant sans cette preuve est une collision. Un reformatage bénin
par KiCad n'enlève pas cette preuve ; une modification de champ l'invalide.
Les formats inconnus, champs dupliqués, liens et fichiers spéciaux sont refusés.

Avant le premier remplacement, un journal durable sous `<cible>/.fabparts/operations`
contient les deux tables exactes en base64, leur absence éventuelle et les états
avant/après. Son sceau est relu ; une copie est conservée dans le workspace.
Un verrou sérialise les instances FabParts. Les remplacements individuels utilisent
un renommage exclusif ou échange atomique, avec conservation des inodes déplacés
et vérification des octets concurrents. Aucune écriture aveugle de la paire.
Une interruption laisse un état RECOVERY_REQUIRED ; une confirmation distincte
restaure les octets antérieurs ou leur absence. Une modification externe inconnue
est conservée et requiert une intervention manuelle. Aucun rollback automatique.
La récupération reste accessible même si l'historique M7 est illisible.

TECH-04A sauvegarde déjà tout `config`, les assets et les publications. Sa restauration
ne touche pas les tables externes : le miroir génération/opération détecte le décalage,
et une activation explicite réconcilie les chemins. Les anciennes générations et
copies restent conservées. Il n'y a pas de purge automatique.

## Interface et utilisation

La section Intégration KiCad de Publications distingue version active, dernière
publication, cible, mise à jour disponible, erreur, reprise et réconciliation.
Installation, changement de version, retour à la précédente et vérification sont
explicites. Résumé puis case vide précèdent toute application ; les chemins longs
et détails de configuration sont repliés. Une réponse incertaine provoque une
lecture de l'état durable, jamais une répétition automatique de la mutation.
Publication et activation sont deux décisions indépendantes.

FR/EN, thèmes et composants FabApps existants réutilisés. Vérification native
1440 × 900 et environ 901 × 949 points, clair anglais et sombre français.
Fermer KiCad avant modification, puis le relancer : aucun rechargement automatique
n'est promis. La vérification d'installation est ponctuelle et remise à zéro lors
d'une actualisation ou d'un échec.

## Qualification et preuves

- Python : **588 tests** (dont 32 contrôles ciblés d'intégration), FreeCAD activé.
- Rust : **32 tests** ; `cargo fmt --check` conforme.
- Frontend : **79 tests TECH + 12 tests UX** ; Svelte : 0 erreur, 0 warning.
- Ruff, formatage et mypy conformes ; paquet Tauri ARM64 avec sidecar reconstruit.
- Configuration entièrement isolée : absence de tables, tiers, deux collections,
  activation/rollback, collisions, concurrence avant/pendant échange, malformation,
  permissions, interruption/reprise, corruption M7, chemins 3D/PDF, readonly,
  sauvegarde/restauration puis réconciliation. Les tests comparent les octets,
  l'absence et les hashes historiques, pas seulement les messages de succès.
- Computer Use : LabParts v1 → v2 → v1 avec consentement séparé ; installation
  PersonalParts ; vérification après rollback ; reprise exacte de la paire après
  interruption, y compris avec manifeste synthétique illisible. Le manifeste
  volontairement corrompu dans la fixture a été restauré depuis ses octets conservés.
- Computer Use readonly : actions de mutation désactivées ; les 162 fichiers de la
  copie figée et de la configuration isolée sont identiques, sans ajout après fermeture.
- KiCad **10.0.7 macOS ARM64** : deux bibliothèques globales visibles ; symbole LabParts
  et empreinte PersonalParts chargés depuis leurs nicknames, modèle WRL orange
  réellement affiché dans la visionneuse 3D. Aucune ressource enregistrée depuis KiCad.
  Écritures FabParts désactivées lorsque KiCad est ouvert.

Captures : [résumé sombre](tech05b/activation-summary-dark.jpg),
[rollback vérifié](tech05b/rollback-verified-dark-fr.jpg),
[anglais clair réduit](tech05b/integration-light-en-narrow.jpg),
[reprise indépendante de M7](tech05b/recovery-source-unavailable.jpg),
[KiCad ouvert](tech05b/kicad-open-blocked.jpg),
[symbole global](tech05b/kicad-global-symbol.jpg),
[empreinte globale](tech05b/kicad-global-footprint.jpg),
[modèle 3D global](tech05b/kicad-global-3d.jpg),
[lecture seule](tech05b/readonly-integration.jpg),
[reprise du paquet final](tech05b/final-package-recovery.jpg).
Les assets sont des fixtures synthétiques de résolution, pas des composants qualifiés
pour fabrication ; leurs dessins minimaux ne constituent pas une validation électrique.

## Correction finale de revue Product Owner

La récupération vérifie désormais la Collection propriétaire inscrite dans le
journal scellé, à la préparation du résumé et de nouveau lors de son application.
Une demande pour une autre Collection est refusée avant toute écriture des tables,
même indépendamment du rattachement de la capacité de session. La reprise par la
Collection propriétaire reste possible. Aucun changement d'architecture ou d'UI.

Les tests injectent aussi une interruption après l'engagement du nouvel état global
mais avant le miroir workspace, pour une première installation et une mise à jour.
Après recréation de l'adaptateur, la version engagée et son historique restent
visibles avec RECONCILE_REQUIRED ; aucune restauration automatique ni réécriture
externe à la lecture/préparation. L'activation explicite réconcilie le miroir,
conserve tout l'historique d'opérations et M7 et réutilise la copie vérifiée sans
modifier les octets ni la date de modification des tables. Ce comportement existant
n'a pas nécessité de changement de logique.

Validation de cette correction : 32 tests d'intégration ciblés, suite Python complète
588 tests avec FreeCAD, Ruff/formatage et mypy conformes. Rust, Svelte et les parcours
natifs restent inchangés ; leurs résultats ci-dessus proviennent de la qualification
TECH-05B précédente, sans nouvelle inspection visuelle pour cette correction backend.

## Limites et conditions

- Qualification native limitée à macOS ARM64/KiCad 10.0.7. Détection dans les quatre
  emplacements Applications usuels, cibles 6.0 à 10.0 ; autres installations à qualifier.
  Les plafonds de formats empêchent d'envoyer un asset récent à un KiCad plus ancien ;
  aucune conversion descendante. Hôte Windows/Linux non livré par ce prototype.
- La grammaire de tables de KiCad 10 refuse les commentaires : ceux-ci sont refusés
  sans modification sur cette cible. Les commentaires `#` de ligne des formats
  antérieurs sont conservés ; `;` n'est pas accepté comme commentaire KiCad.
  Cette différence a été révélée par la qualification réelle : la première fixture
  contenait un commentaire invalide et KiCad a proposé de recréer ses tables.
  FabParts a détecté le changement. Les seules tables factices ont ensuite été
  rétablies dans un format compatible ; les tables personnelles n'ont pas été touchées.
- Un filesystem doit fournir le renommage atomique exclusif/échange. Pas de fallback
  non atomique. Le verrou est coopératif ; les changements concurrents inattendus
  sont conservés avec intervention manuelle, pas fusionnés automatiquement.
- Les copies et journaux sont conservés sans purge. Affichage borné aux 50 premières
  collections installées et 20 dernières activations de la collection ; l'historique
  durable complet reste sur disque. Les journaux documentent aussi les interruptions.
- Une fermeture de KiCad détectée par processus n'est pas une promesse de contrôle
  de tous les outils tiers ou d'un writer qui démarre après cette détection.

### Incident de qualification déclaré

La première sonde `kicad-cli version`, avant son isolation corrigée, a réécrit le
fichier personnel `~/Library/Preferences/kicad/10.0/kicad_common.json`. Les octets
antérieurs n'avaient pas été sauvegardés : aucune restauration approximative n'a
été tentée. L'utilisateur a été informé. Les véritables tables globales sont restées
inchangées, y compris leur absence initiale dans la configuration 10.0.
La correction isole les deux variables de configuration/documents et dispose d'un
test de régression Rust. Les préférences après cet incident n'ont plus changé lors
des qualifications suivantes. Les 9 fichiers personnels de l'ancien KiPart Manager
sont inchangés et aucun workspace FabParts personnel réel n'a été créé.

## Sources primaires de compatibilité

- [KiCad : chemins, variables et redémarrage](https://docs.kicad.org/7.0/en/kicad/kicad.html).
- [KiCad 10 : calcul des chemins de configuration](https://github.com/KiCad/kicad-source-mirror/blob/10.0.0/common/paths.cpp).
- [KiCad 10 : grammaire des tables](https://github.com/KiCad/kicad-source-mirror/blob/10.0.0/include/libraries/library_table_grammar.h).
- [KiCad : historique de formats symboles](https://docs.kicad.org/doxygen/sch__file__versions_8h_source.html).
- [KiCad 9 : historique de formats empreintes](https://github.com/KiCad/kicad-source-mirror/blob/9.0.0/pcbnew/pcb_io/kicad_sexpr/pcb_io_kicad_sexpr.h).
- [Apple : échange atomique](https://developer.apple.com/documentation/foundation/urlresourcekey/volumesupportsswaprenamingkey),
  [renommage exclusif](https://developer.apple.com/documentation/foundation/urlresourcevalues/volumesupportsexclusiverenaming).

**GO WITH CONDITIONS** : parcours qualifié dans l'environnement ci-dessus ; garder
les refus conservateurs pour les formats, conflits, plateformes et filesystems non
qualifiés. L'incident de préférences doit rester visible dans la revue de PR.
PR à main, sans fusion automatique. STOP avant TECH-06.
