# FabParts 2.0 — TECH-04B : validation technique

Date : 26 octobre 2026. Branche : `tech/04b-component-validation`.

## Base et périmètre

PR TECH-04A #4 fusionnée avec **Create a merge commit**, commit
`0065a8ef63324f0f4480720432ce084f8f43106e` (parents `a0c850a` et `2f587e8`).
Checkout propre synchronisé sur `origin/main` avant création de la branche.
Le commit TECH-04A et sa base n'avaient pas changé depuis leurs validations ;
GitHub n'exposait aucun statut/check CI. Aucun conflit, aucune protection contournée.

LocalValidation, LocalResourceProbe et SqliteValidationReports sont composés dans
le sidecar personnel/sandbox. En readonly, les mêmes sondes lisent sans initialiser
l'Asset Store ni l'index ; seul l'enregistrement de rapport est interdit. Aucun
parseur, règle M5, schéma ou état métier n'a été réécrit. Aucune bibliothèque KiCad
n'est produite, installée ou synchronisée.

## Contrats IPC v1

| Host Tauri | Python privé | Paramètres |
| --- | --- | --- |
| `get_validation` | `validation_get` | query `{kind, id, offset?, member_offset?}` |
| `run_validation` | `validation_run` | subject `{kind, id}` |
| `accept_validation_warnings` | `validation_accept` | subject `{kind, id}` + handle opaque |

`kind` vaut Part ou Collection ; UUID et paramètres stricts aux deux frontières.
Les offsets sont bornés à 1 000 000 ; pages de 100 constats et 50 membres. Chaque
message est tronqué à 2 048 caractères pour borner le transport ; les détails
complets restent dans le rapport M5 persistant. L'enveloppe conserve ses limites
16 Kio / 2 Mio. Aucun champ n'autorise un résultat, une empreinte ou un rapport fourni
par la WebView. Les écritures sont refusées readonly, pendant une préparation
active et après une restauration exigeant un redémarrage.

La lecture recalcule la qualification pour détecter STALE. Un rapport actuel contenant des WARNING reçoit une capacité aléatoire liée à la session, au sujet et au rapport
exact (dont sa date). Maximum 32 rapports examinés en mémoire. L'acceptation compare
à nouveau le rapport enregistré et la qualification, puis appelle la politique
existante `LocalValidation.validate(accept_warnings=True)` ; aucune acceptation
automatique. Accepter les WARNING ne résout pas les ERROR du même rapport. Une validation neuve remet l'acceptation à zéro, comme M5.

L'interface exige affichage du rapport, examen des avertissements et case explicite.
Toutes les pages de constats doivent avoir été affichées avant confirmation. Une
réponse différente ou périmée réinitialise cette confirmation. Les commandes sont
asynchrones pour la WebView ; une génération de vue ignore les réponses tardives.
Le host sérialise l'accès au moteur ; 300 s maximum pour ces lectures/inspections.
Un timeout ferme la session et ne vaut jamais succès. Les heartbeats sont suspendus
pendant une validation visible ; aucun thread ne partage une Session SQLAlchemy.

## Projection des statuts utilisateur

La préparation technique est indépendante de DRAFT / IDENTIFIED / DEPRECATED et
de l'état global UNCHECKED des assets. Une sélection ou un aperçu ne prouve rien.

| Statut | Preuves nécessaires |
| --- | --- |
| À compléter | Rapport absent, obsolète, lecture impossible ou symbole insuffisamment contrôlé |
| Prêt pour schéma | Rapport M5 actuel ; symbole sélectionné avec constat RESOURCE PASS ; composant non déprécié ; WARNING du symbole accepté s'il en existe |
| Prêt pour PCB | Qualification M5 actuelle et éligible : aucun ERROR, aucun WARNING non accepté |

La petite projection `ValidationReview` réutilise les constats enregistrés et les
choix métier, sans appeler un nouveau parseur ni assouplir M5. Le manque de package
ou footprint, une erreur de footprint ou de mapping peuvent laisser un symbole
prêt pour schéma ; ils ne permettent jamais de conclure prêt pour PCB. Si les
données changent, même le statut schéma devient À compléter jusqu'à revalidation.
La date du rapport et les limites de couverture sont visibles. Le contrôle est
ponctuel à l'ouverture/actualisation, pas un watcher filesystem permanent.

Le modèle 3D reste facultatif et la datasheet recommandée. S'ils sont sélectionnés,
leurs erreurs et WARNING M5 participent à la qualification PCB ; un lien 3D sans
modèle conserve son WARNING historique, qui exige une décision explicite. Les
contrôles ne certifient pas la fonction électrique, les espacements/DRC ou l'ajustement
mécanique. « Prêt » désigne les contrôles couverts, pas une certification générale.

## Interface

Section Validation technique dans la fiche ; synthèse dans l'inspecteur. Résultats
par ressource/cohérence globale, date, gravités, contrôles réussis repliés, actions
Valider / Actualiser / Vérifier si le rapport est actuel / Examiner les avertissements.
Les quatre previews restent dans la fiche. Les tokens et composants existants sont
réutilisés. Tous les nouveaux contrôles et résumés sont FR/EN ; les diagnostics
historiques détaillés du moteur peuvent rester en français.

Pour une bibliothèque sélectionnée, Qualification de la bibliothèque ouvre un
rapport simple avec nombre de composants, erreurs/avertissements par membre et
accès aux fiches concernées. Ce rapport est indépendant des rapports individuels :
valider une collection ne crée pas silencieusement des rapports Part.

## Vérifications

Vérifications réalisées sur données jetables :

- pytest complet : **540 tests réussis**, aucun ignoré, avec `FABPARTS_TEST_FREECAD=1`.
- Rust : **28 tests réussis**, rustfmt sans différence.
- Frontend TECH : **56 tests réussis** ; prototype UX : **12 réussis**.
- Svelte : **0 erreur / 0 avertissement** ; Ruff, format et mypy : succès (174 modules).
- PyInstaller et paquet Tauri release macOS : builds réussis (avertissement Vite
  de taille de chunk hérité).

Les 20 tests ajoutés couvrent composant incomplet, symbole sans footprint,
cohérence PCB, pins/pads incompatibles, fichiers absents/corrompus, WARNING et
confirmation exacte (y compris WARNING au sein d'un rapport ERROR), rapport
STALE/remplacé, capacité d'une session précédente, composant déprécié, ressource
générée, collection avec membre invalide, pagination, persistance après restauration,
préparation active et blocage après restauration. Un vrai processus readonly relit
un rapport enregistré sans modifier un seul hash du dossier et refuse les mutations.
Les tests historiques d’ingestion, migrations, snapshots et quatre previews passent.
Les tests frontend couvrent confirmation non précochée, examen préalable, toutes
les pages, double clic, erreurs sans faux succès et réponses tardives.

Le sidecar PyInstaller final a aussi été testé en vrai processus sur copies
jetables : cinq cas Part, validation Collection, acceptation WARNING, persistance
et relecture readonly. Les résultats attendus sont obtenus ; les hashes de la
copie readonly sont inchangés et Qt n’est pas chargé. Les processus du test natif
initial ont été arrêtés ; aucun host, sidecar ou worker lancé pour ce test ne reste
actif. Les **9 fichiers historiques sont inchangés** ; le dossier système FabParts
reste absent comme au début du jalon.

## Inspection native macOS — Computer Use

Qualification du paquet release et du sidecar embarqué sur cinq cas jetables,
après déverrouillage de la session par l'utilisateur. Aucune donnée historique
ouverte writable. Fenêtre normale 1440×900 points, fenêtre agrandie, puis fenêtre
réduite par le menu natif macOS à environ 901×949 points ; thèmes clair/sombre et
libellés FR/EN inspectés. Actions, textes longs, repliements, focus et confirmation
non précochée restent utilisables ; aucun débordement observé.

| Cas inspecté | Résultat observé |
| --- | --- |
| Quatre ressources sélectionnées | Aucun statut prêt sans rapport ; WARNING puis Prêt pour schéma |
| Revue des trois WARNING | Bouton désactivé avant confirmation ; acceptation explicite → Prêt pour PCB ; état métier Brouillon conservé |
| Symbole seul | Prêt pour schéma, erreurs PCB pour package/footprint manquants |
| Symbole et footprint cohérents | PASS et Prêt pour PCB sans 3D ni datasheet |
| Pin 9 absente du footprint | Erreur visible ; accepter le WARNING de pads supplémentaires ne permet pas Prêt pour PCB |
| Composant sans ressources | À compléter, trois erreurs explicites |
| Métadonnée changée via l'assistant TECH-03 | Rapport STALE et À compléter ; contrôle d'actualité conserve STALE ; nouvelle validation requise pour retrouver Prêt pour PCB |
| Bibliothèque contenant les cinq cas | Membres bloquants identifiés, rapports indépendants ; modification d'un membre rend le rapport Collection STALE |
| Fermeture puis réouverture personnelle | Rapport, date et acceptation conservés ; arrêt coopératif du sidecar, exit 0 |
| Copie readonly native | Lecture et quatre previews disponibles ; aucune commande Valider/Accepter ; hashes des 10 fichiers identiques après fermeture |

Les cartes de ressources distinguent maintenant association/aperçu et qualification
du composant, sans modifier l'état global des assets. Les textes d'aide évitent les
identifiants de milestone et le vocabulaire « workspace writable ».

Captures natives finales :

- [Rapport et WARNING acceptés, sombre](tech04b/warning-accepted-dark.jpg)
- [Quatre aperçus après validation](tech04b/four-previews-dark.jpg)
- [Bibliothèque en clair, fenêtre réduite](tech04b/collection-light-narrow.jpg)


## Limites

macOS ARM64 seul qualifié. Inspections M5 synchrones côté moteur et sérialisées ;
les grands catalogues peuvent être lents. Pas d'annulation d'un enregistrement
déjà commencé. Pas de rapport historique multiple ni de nouvelle infrastructure de
persistance. Les limites et réserves du workspace TECH-04A restent applicables.

TECH-05 hors périmètre. TECH-04B ne sera pas fusionné automatiquement.

## État de livraison

**GO WITH CONDITIONS** : critères fonctionnels, contrats et inspection native
vérifiés. Réserves : macOS ARM64 seulement, couverture M5 partielle, diagnostics
historiques détaillés parfois en français et coût des grandes collections.
Aucune certification électrique/mécanique exhaustive ni qualification d'une autre
plateforme n'est revendiquée. Les réserves de récupération TECH-04A restent applicables.

PR #5 vers `main`, prête pour revue, sans merge automatique. Arrêt à TECH-04B.
