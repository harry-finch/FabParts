# FabParts 2.0 — Spécification UX initiale

**Document :** `docs/UX_SPEC.md`  
**Version :** 0.1 — proposition soumise à validation produit  
**Date :** 24 octobre 2026  
**Périmètre :** expérience utilisateur cible, indépendamment du choix définitif PySide6 ou Tauri  
**Référence technique :** [architecture du moteur et du prototype](ARCHITECTURE.md).

> **Promesse produit :** « Je retrouve mes composants, j'en ajoute un avec ce que je possède, je vérifie visuellement les ressources proposées, et il devient utilisable dans KiCad sans manipulation répétitive de bibliothèques. »

## 1. Décisions produit déjà validées

1. **FabParts est la source unique de vérité** pour le catalogue, les ressources et leurs versions validées. Les bibliothèques vues par KiCad sont des sorties gérées, pas l'endroit où l'on modifie directement les données canoniques.
2. **Simple en surface.** L'interface expose les tâches — parcourir, rechercher, ajouter, vérifier, utiliser dans KiCad — et non les entités internes (`Part`, `Package`, `Asset`, `Publication`, etc.). Les fonctions avancées restent accessibles sans dominer l'écran.
3. **Bibliothèques visibles et recherche transverse.** `Lab`, `Personnel` et futures bibliothèques peuvent être consultées séparément ; « Toutes les bibliothèques » recherche dans l'ensemble. Un composant commun à plusieurs bibliothèques apparaît une seule fois dans le résultat global, avec ses appartenances visibles.
4. **Classification commune** pour toutes les bibliothèques, avec catégorisation proposée automatiquement et correction manuelle possible.
5. **Liste compacte + panneau de détails** dans l'écran principal ; une fiche plus complète est accessible pour inspecter ou modifier.
6. **Ajout guidé depuis n'importe quel élément disponible :** référence, fabricant, datasheet, symbole, footprint, modèle STEP/WRL ou combinaison de ces entrées. La recherche de ressources existantes précède toute génération.
7. **Confirmation groupée :** après l'identification et la confirmation éventuelle du boîtier, symbole, empreinte, modèle 3D et datasheet sont affichés **ensemble** dans une vue d'ensemble. Pas de validation modale à chaque résultat.
8. **Brouillons autorisés.** Un composant incomplet peut être conservé dans FabParts. États lisibles : `À compléter`, `Prêt pour schéma` (symbole adapté validé), `Prêt pour PCB` (symbole et empreinte compatibles et validés). Le STEP est facultatif ; la datasheet recommandée, non systématiquement bloquante.
9. **Synchronisation automatique vers les bibliothèques globales KiCad** après toute modification validée et publiable, avec sauvegarde de la version précédente, protections contre les écritures partielles et visibilité de l'état de synchronisation. L'installation/configuration initiale peut nécessiter une action explicite.
10. **KiCad conserve ses copies dans les projets.** Ne pas réinventer un système parallèle de « bibliothèque figée par projet » dans le MVP. Un export autonome des dépendances externes reste possible plus tard.
11. **Édition aller-retour.** Une ressource pourra être modifiée dans l'éditeur KiCad sur une copie de travail, puis réimportée après inspection, validation, détection des conflits et enregistrement d'une nouvelle version. Cette capacité n'est pas encore implémentée.
12. **Local-first.** Pas de serveur, d'Internet ou d'IA cloud obligatoire. Les fichiers utilisateur sont copiés dans l'Asset Store géré. L'IA, les fournisseurs et la synchronisation réseau sont facultatifs.

## 2. Règles UX transversales

- **Action principale évidente** : « Ajouter un composant » dans la bibliothèque ; ensuite « Rechercher et analyser », puis « Enregistrer dans… ».
- **L'application propose ; l'utilisateur décide.** Identification, package, ressources, changements ou conflits importants sont confirmés ; aucune source fournie n'est remplacée silencieusement.
- **Progressive disclosure** : listes, aperçus et actions simples d'abord ; numéros de pins, IDs, hashes, provenance détaillée, versions et rapports dans « Détails techniques ».
- **Une source affichée par proposition** : KiCad officiel, fichier utilisateur, catalogue géré, constructeur, SnapMagic, généré, etc. Ne jamais assimiler « trouvé » à « validé ».
- **Pas de score arbitraire** : utiliser « correspondance exacte », « probable » ou « à vérifier », avec justification vérifiable.
- **L'utilisateur peut enregistrer un brouillon et revenir plus tard** ; aucune recherche manquante ou panne réseau ne fait perdre les données saisies.
- **Les actions longues sont non bloquantes**, présentent progression/annulation lorsque techniquement sûres, et distinguent « recherche en cours », « rien trouvé », « non configuré » et « erreur ».
- **Même langage de design** : `fab-design-system` est l'autorité visuelle et `professional-workshop-ui` définit les conventions de l'outil technique ; conserver le graphite et l'accent jaune/ambre. Lire leurs fichiers réels dans le dépôt avant de fixer les tokens et composants.
- **Accessibilité** : texte et icône en complément des couleurs, focus visible, navigation clavier, contrastes suffisants, tooltips pour les termes techniques.

## 3. Navigation et architecture d'information

L'application s'ouvre sur les **bibliothèques de composants**. Le menu principal ne doit pas reproduire les tables SQL.

Navigation initiale proposée :

- **Bibliothèques** (écran d'accueil) : `Toutes`, `Lab`, `Personnel`, autres bibliothèques, commande de création/gestion.
- **Activité / synchronisation** : indicateur discret et accessible depuis l'en-tête ; historique, problèmes et réparation si nécessaire, plutôt qu'un écran principal de « publications ».
- **Paramètres** : installation KiCad, répertoires, providers, option IA, chemins et diagnostic.

`Packages`, `Assets`, `Collections`, `StockItem`, `Publication`, `Resolver` et leurs paramètres ne sont pas des entrées principales. Les fonctions d'inventaire détaillé pourront être présentées dans les fiches/bibliothèques ou ajoutées ultérieurement si l'usage le justifie.

### 3.1 Écran A — Bibliothèques / recherche

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ FabParts                                         KiCad ✓ à jour      ⚙     │
├─────────────────┬──────────────────────────────────────────────────────────┤
│ BIBLIOTHÈQUES   │ Composants                         [+ Ajouter]            │
│                 │ [ Rechercher référence, fonction, fabricant…          ]   │
│ ● Toutes        │ [Catégorie ▾] [Package ▾] [État ▾] [Bibliothèque ▾]       │
│   Lab           ├───────────────────────────────┬──────────────────────────┤
│   Personnel     │ Composant      Package  État  │ STM32F103C8T6             │
│   + Nouvelle    │                               │ ST · Microcontrôleur      │
│                 │ > STM32…       LQFP-48  PCB ✓ │ [Lab] [Personnel]         │
│ CATÉGORIES      │   ADS1115…     VSSOP-10 PCB ✓ │                          │
│   Microcontrôl. │   NE555P       DIP-8    …     │ Symbole      ✓ Voir      │
│   Connecteurs   │   ...                         │ Empreinte    ✓ Voir      │
│   Résistances   │                               │ Modèle 3D    – Ajouter   │
│   …             │                               │ Datasheet    ✓ Ouvrir    │
│                 │                               │                          │
│                 │                               │ [ Ouvrir la fiche ]      │
└─────────────────┴───────────────────────────────┴──────────────────────────┘
```

**Comportement :**

- Le choix d'une bibliothèque et les filtres modifient les résultats sans changer le sens de l'écran ; « Toutes » agrège et déduplique les composants.
- Recherche sur MPN, fabricant, nom, description, catégories, références secondaires et propriétés disponibles. Pas de promesse de recherche sémantique IA sans implémentation effective.
- Colonnes utiles : composant, fabricant (selon largeur), package, état, bibliothèque(s) ; UUID caché en mode normal.
- Un clic sélectionne et renseigne le panneau de droite ; double-clic/« Ouvrir la fiche » affiche les détails complets.
- Panneau redimensionnable ; à largeur réduite, bascule vers détail dans une page/panneau plutôt que compresser les deux colonnes.
- État vide explicatif avec bouton d'ajout ; état sans résultats avec « Effacer les filtres » ; état chargement/erreur géré.
- Favoris, tags personnalisés et vues multiples ne font pas partie du premier prototype sans preuve de besoin.

### 3.2 Écran B — Ajouter un composant

Ce n'est **pas un wizard de dix pages**. Un point d'entrée, une identification éventuelle du package, puis un écran de validation globale.

**B1 — Saisie libre des éléments disponibles**

```text
┌────────────────────────────────────────────────────────────┐
│ Ajouter un composant                                      │
│                                                            │
│ Que connais-tu de ce composant ?                            │
│ [ Référence / MPN (facultatif)                           ]  │
│ [ Fabricant (facultatif)                                  ]  │
│                                                            │
│ Ou dépose ce que tu possèdes :                              │
│ [ PDF datasheet ] [ Symbole ] [ Empreinte ] [ STEP/WRL ]     │
│                                                            │
│ Bibliothèque(s) : [Lab ☑] [Personnel □]                     │
│                                          [Analyser →]       │
└────────────────────────────────────────────────────────────┘
```

- Les champs et fichiers sont facultatifs individuellement ; il faut seulement assez d'informations pour créer un brouillon identifiable.
- Plusieurs fichiers peuvent être déposés ; rôle proposé automatiquement, modifiable en cas d'ambiguïté.
- Les fichiers utilisateur acceptés sont copiés dans l'Asset Store ; jamais de lien vivant vers `Téléchargements`.
- La bibliothèque cible est choisie sans exiger de comprendre la différence technique entre collection et inventaire.

**B2 — Identification et package**

- Résultat proposé avec fabricant, MPN, description, catégorie, sources et niveau de certitude justifié.
- Si MPN précis = package identifié de façon fiable : package présélectionné, correction accessible.
- Si référence générique ou plusieurs variantes : afficher des choix de boîtiers reconnaissables (DIP-8, SOIC-8, etc.), leurs dimensions et source.
- Si ambigu : aucune décision silencieuse ; permettre un brouillon à compléter.
- Si un composant existe déjà : proposer « Voir l'existant », « Ajouter à une autre bibliothèque » ou « Créer une variante » ; ne pas créer un doublon par défaut.

**B3 — Recherche orchestrée**

- Réutiliser les assets fournis, les assets gérés et les bibliothèques KiCad officielles locales d'abord, puis les sources distantes autorisées ; aucune génération avant recherche.
- Afficher des mises à jour progressives et l'origine de chaque candidat. L'utilisateur peut inspecter une proposition découverte sans attendre la fin de toutes les recherches.
- Les résultats réseau/IA ne sont disponibles que si les services sont configurés et consentis. Ne pas inventer de succès fournisseur.

**B4 — Vue d'ensemble des quatre ressources (décision validée)**

```text
┌───────────────────────────────────────────────────────────────────────┐
│ STM32F103C8T6 · STMicroelectronics · LQFP-48            [Modifier]    │
│                                                                       │
│  ┌───────────────────────┐ ┌───────────────────────┐                   │
│  │ SYMBOLE       ✓       │ │ EMPREINTE      ✓      │                   │
│  │ [ aperçu réel ]       │ │ [ aperçu réel ]       │                   │
│  │ KiCad officiel        │ │ KiCad officiel        │                   │
│  │ [Voir] [Changer]      │ │ [Voir] [Changer]      │                   │
│  └───────────────────────┘ └───────────────────────┘                   │
│  ┌───────────────────────┐ ┌───────────────────────┐                   │
│  │ MODÈLE 3D     absent  │ │ DATASHEET       ✓     │                   │
│  │ [ Ajouter / chercher] │ │ [ Aperçu PDF ]        │                   │
│  └───────────────────────┘ └───────────────────────┘                   │
│                                                                       │
│  Statut : Prêt pour PCB · Modèle 3D facultatif                         │
│  Bibliothèques : [Lab ✓] [Personnel □]                                 │
│                                     [Enregistrer dans FabParts]        │
└───────────────────────────────────────────────────────────────────────┘
```

- Afficher **simultanément** symbole, empreinte, modèle 3D et datasheet avec vrais aperçus lorsqu'ils sont disponibles, sinon un état explicite (« aperçu non pris en charge », « manquant »).
- Chaque carte indique source, sélection, état de validation, avertissements, et `Voir` / `Changer` / `Importer` pertinents.
- Clic sur `Voir` : panneau grand format zoomable et détails techniques ; comparer deux candidats sans perdre la vue d'ensemble.
- Indiquer clairement les relations `Part → Package → Footprint → modèle 3D` dans les détails sans obliger l'utilisateur à manipuler toutes ces entités.
- Une erreur bloquante empêche le statut prêt correspondant, **mais pas l'enregistrement d'un brouillon**.
- Les composants peuvent être enregistrés incomplets et récupérés plus tard.
- Enregistrer ne signifie pas que toutes les ressources ont été publiées ; l'état de préparation et la synchro sont affichés séparément.

### 3.3 Écran C — Fiche composant complète

La fiche est accessible depuis la liste et après création. Elle est l'espace d'inspection/édition détaillée ; elle reste organisée par usages.

**En-tête :** nom/MPN, fabricant, catégorie, package, appartenances, statut de préparation, état de synchronisation, actions `Modifier`, `Rechercher des ressources`, `Retirer de la bibliothèque` (action prudente).

**Contenu :**

- Résumé technique lisible : description, variantes, boîtier, propriétés pertinentes ; propriétés avancées repliables.
- Même grille des quatre ressources, avec aperçus, source, validité et associations.
- Détails de provenance et datasheet (page source si réellement connue).
- Inventaire simplifié par bibliothèque si utilisé : quantité, emplacement, sans confondre possession et mise à disposition dans KiCad.
- Historique de versions/validation accessible en second niveau.

**Modification dans KiCad (cible future, pas acquise) :**

1. `Modifier dans KiCad` crée une **copie de travail** de l'asset choisi ; jamais d'édition du blob canonique ou d'une publication immuable.
2. L'éditeur KiCad approprié est lancé dans la mesure où l'intégration le permet ; un fallback de sélection manuelle peut être nécessaire.
3. Après sauvegarde, l'utilisateur sélectionne `Réimporter les modifications`.
4. FabParts compare **base de session / état courant / fichier modifié**, détecte conflits et changements du package partagé, propose `Mettre à jour la ressource partagée` ou `Créer une variante` selon les impacts.
5. Après validation : nouveau fichier géré, ancienne version conservée, nouvelles validations, puis synchro d'une nouvelle version publiable.

## 4. États utilisateur (distincts)

### 4.1 État de préparation d'un composant

| État affiché | Règle fonctionnelle cible |
|---|---|
| **À compléter** | Part enregistrée, mais éléments nécessaires absents, ambigus ou non validés |
| **Prêt pour schéma** | Symbole pertinent et validé ; pas nécessairement de footprint prêt |
| **Prêt pour PCB** | Symbole et footprint pertinents, mapping cohérent/validé, absence d'erreur bloquante |

Le modèle 3D est facultatif ; la datasheet est recommandée. Si un rapport de validation devient périmé après modification, l'état « prêt » doit être réévalué. Cette nomenclature est un **contrat d'UX cible**, pas une affirmation que les états métiers existants correspondent déjà exactement.

**Clarification produit — TECH-01 :** accepter une ressource signifie sélectionner une proposition. Cela ne constitue pas une validation technique. Un composant ne devient prêt pour schéma ou PCB qu’après les contrôles requis.

### 4.2 État de synchronisation KiCad (indépendant)

`Non configuré` · `À jour` · `Synchronisation en cours` · `Mise à jour en attente` · `Erreur — réessayer` · `Version précédente conservée`.

- Seules les ressources publiables rejoignent les bibliothèques globales KiCad.
- Publication locale atomique et versionnée, avec sauvegarde de la configuration utilisateur KiCad avant la première installation.
- Ne jamais écraser les entrées de bibliothèques tierces ; préserver la possibilité de retour arrière.
- Une version validée mise à jour dans FabParts devient disponible pour les **nouveaux placements** dans KiCad ; les symboles/empreintes déjà placés dans les projets ne sont pas modifiés silencieusement.
- Si KiCad doit être relancé/rafraîchi pour voir un changement, le signaler sans promettre une disponibilité instantanée.

## 5. Cas limites et comportements attendus

| Situation | UX attendue |
|---|---|
| MPN ambigu ou non trouvé | Proposer alternatives et sources ; édition manuelle ; brouillon enregistrable |
| Plusieurs packages | Sélection explicite et aperçu pertinent, avec package prérempli si certitude suffisante |
| Asset fourni différent d'un asset KiCad | Montrer les deux, provenance et aperçu ; choix explicite, pas de remplacement automatique |
| Ressource absente | Carte « manquant » avec options `Rechercher`, `Importer`, `Plus tard` |
| Asset importé non valide | Indiquer « importé, non validé » ; conserver le brouillon et le diagnostic |
| 3D absent | Ne pas bloquer `Prêt pour PCB` si le symbole/empreinte sont validés |
| Connexion coupée / provider absent | Recherche locale encore disponible ; message clair, sans modal bloquante |
| Datasheet PDF inexploitable | Ouvrir le PDF si possible, permettre identification manuelle ; ne pas inventer de champs |
| Composant déjà existant | Proposer ajout à la bibliothèque sélectionnée plutôt que duplication |
| Asset partagé modifié | Montrer les composants impactés et proposer nouvelle variante |
| Recherche/synchronisation longue | Progrès et annulation sûre lorsque possible, sans interrompre une écriture critique |
| Collision de nom dans KiCad | Ne pas modifier les autres bibliothèques ; diagnostic et solution guidée |
| Modifications concurrentes | Refuser remplacement aveugle ; montrer versions et options de résolution |

## 6. Design system, contenu et adaptativité

- Le prototype doit **lire réellement** `.codex/skills/fab-design-system/` (ou l'emplacement effectif du pack) et `professional-workshop-ui` dans le dépôt. Ce document ne prétend pas retranscrire leur contenu exact.
- Utiliser les tokens existants, sans second système de style. Graphite commun FabApps ; ambre/jaune KiPart/FabParts pour les actions/sélections, pas pour les erreurs ou succès sémantiques.
- Navigation clavier, focus visible, boutons avec libellés explicites, champs associés à leurs erreurs.
- Favoriser listes denses mais lisibles, tables triables si pertinentes, panneaux redimensionnables, conservation des filtres et de la sélection.
- Prévoir largeur desktop normale, fenêtre étroite et fenêtre large ; repli du panneau de détails à largeur insuffisante.
- Microtextes d'aide (ex. « Package : boîtier physique ; empreinte : géométrie des pads sur le PCB »), tooltips uniquement comme aide complémentaire.
- Ne pas faire dépendre l'ergonomie de la présence de l'IA ; affichage explicite des sources et confiance justifiée.

## 7. Existant réel et écarts à ne pas masquer

Constats issus de l'audit du dépôt du 24/10/2026 :

| Disponible, avec limites | Non démontré / à construire |
|---|---|
| Domaine et base SQLite distincts de PySide6 ; Asset Store SHA-256 ; inventaires, collections et versions | Parcours unifié d'ajout d'un composant depuis référence/PDF jusqu'aux assets |
| Index KiCad, resolver local, validations partielles, publication/export déterministe | Recherche et récupération automatique exhaustive des ressources, validation électrique/mécanique complète |
| Aperçus symboles/footprints/PDF, et 3D sous conditions | Fidélité totale des prévisualisations et superposition 3D/empreinte |
| Métadonnées et propositions IA relues | Lecture autonome de datasheet et extraction complète fiables |
| Adaptateur SnapMagic partiellement préparé | Client partenaire réel et droits de distribution établis |
| Bibliothèques produites et transférables | Installation/mise à jour automatique des bibliothèques globales KiCad |
| Import d'assets et choix explicites | Session `Modifier dans KiCad → Réimporter` contrôlée |

Ne pas présenter les éléments de la colonne droite comme des capacités déjà livrées.

**Sécurité préalable obligatoire à tout prototype modifiant le dépôt** : l'audit rapporte une branche `main` sans commit et des fichiers non suivis. Créer une référence Git récupérable et sauvegarder le dossier de données complet (SQLite, blobs, publications, configuration). Un `.kiparts` v1 ne constitue pas une sauvegarde totale du produit.

## 8. Démonstrations utilisateur à valider avant développement général

1. **NE555 en boîtier DIP-8** : MPN générique/ambivalent, choix de boîtier, symboles/footprints officiels proposés, absence éventuelle de 3D sans blocage, ajout à Lab.
2. **STM32F103C8T6** : référence précise, package inféré avec possibilité de correction, visualisation globale des quatre ressources, proposition de composants communs à Lab et Personnel.
3. **Composant spécifique avec fichiers utilisateur** : importer un symbole, un `.kicad_mod`, un STEP et éventuellement le PDF ; vérifier que les fichiers sont gérés sans dépendre du dossier Téléchargements ; enregistrer même si une vérification reste en suspens.
4. **Recherche globale** : retrouver un même composant présent dans deux bibliothèques une seule fois, avec appartenances visibles ; filtre par catégorie et par état.
5. **Publication et erreur** : valider une ressource, visualiser une mise à jour automatique de la bibliothèque, puis simuler un échec pour vérifier la conservation de la version précédemment active.
6. **Édition externe future** : montrer le parcours attendu dans les wireframes et vérifier séparément ce que KiCad autorise avant de promettre l'ouverture automatique sur un asset précis.

## 9. Critères d'acceptation UX (pour prototype)

- L'utilisateur comprend dès l'accueil quelles bibliothèques sont disponibles, comment rechercher et comment ajouter.
- Un composant partagé entre Lab et Personnel n'apparaît pas en double dans « Toutes les bibliothèques ».
- La fiche synthétique donne immédiatement identité, package, préparation, bibliothèques, présence des quatre ressources et état KiCad.
- L'ajout accepte les fichiers existants sans exiger d'abord la création séparée d'entités `Package`/`Asset`.
- Une identité/package ambigus sont confirmés et non devinés silencieusement.
- La vérification finale présente les **quatre ressources simultanément** et permet de comparer/remplacer individuellement.
- Un brouillon incomplet est enregistrable, retrouvable et modifiable.
- La préparation pour schéma/PCB et la synchronisation KiCad sont deux statuts distincts et compréhensibles.
- Les erreurs réseau et l'absence d'IA n'empêchent pas les parcours locaux.
- Le style suit les packs réellement installés et les écrans restent utilisables à plusieurs largeurs desktop.
- Aucune modification des données utilisateurs n'est effectuée lors du prototype UX sans sauvegarde et consentement explicite.

## 10. Frontière de la phase suivante

**Étape suivante après validation de ce document :** wireframes plus précis/prototype cliquable des trois écrans, puis petite preuve de faisabilité Tauri + moteur Python sur une copie du catalogue. Cette spécification ne décide pas encore du protocole IPC, du framework Web ni d'une migration de schéma.

**Hors périmètre immédiat :** génération automatique de symboles/empreintes/STEP, remplacement complet du moteur Python, synchronisation serveur, marketplace fournisseurs, import exhaustif de toute bibliothèque existante, BOM avancée.

**Décisions restant à vérifier par expérimentation, pas par supposition :** installation globale KiCad robuste, lancement d'un éditeur sur une ressource précise, protocole de réimport, transport des previews et packaging Python sidecar sur les OS cibles.

---

**Checkpoint produit :** valider les écrans A/B/C, leur vocabulaire et leurs parcours de bout en bout avant de lancer l'implémentation générale de FabParts 2.0.
