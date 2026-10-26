# TECH-06B — Sources externes facultatives

26 octobre 2026 · `tech/06b-external-sources`

## Base et périmètre

PR #9 vérifiée sans conflit, mergeable, sans statut ni workflow CI publié, puis
fusionnée par **merge commit** `17ce0e27bd262c23ec7969d07c647e8d1cdcb286`.
`origin/main` synchronisé par fast-forward ; branche B créée depuis ce main,
sans écraser de modification locale. Aucun changement M5/M6/M7/TECH-05B ni schéma.

Audit : AGENTS, REMOTE_KICAD, DOCUMENTATION/M10, TECH-06A et ADR 0002/0003/0004.
Skills Fab design system, professional workshop UI, KiCad library workflow,
vérification Python/checkpoint et invariant hors ligne appliquées. Pas de code
PySide modifié ; les composants Svelte et tokens Fab existants sont réutilisés.

## Services, décisions et consentement

`RemoteLibraries`, `OfficialGitLab`, `TomlRemoteSettings`, `Documentation`,
`ManufacturerPDFs`, `ManufacturerSettings`, `AssetImports`, `Ingestion` et
`LocalDiscovery` restent les services de référence. Pas de nouvelle API,
dépendance, moteur de recherche global ou infrastructure réseau parallèle.

La recherche locale reste principale. Le panneau facultatif de la troisième
étape propose type, bibliothèque précise, terme et révision configurée. Un résultat
présente nom, bibliothèque, description, source officielle, révision et commit.
**Examiner**, **télécharger**, **retenir** et **enregistrer** sont des décisions
séparées. Télécharger ne remplace jamais le choix local déjà retenu.

Les réglages sont les TOML M9/M10 existants, disponibles dans Paramètres et dans
le panneau : services désactivés par défaut, aucun domaine PDF préautorisé.
Une URL HTTPS constructeur exige une case de consentement pour ce téléchargement,
réinitialisée après modification de l'URL ou tentative. Aucune extraction PDF.

## Préparation, provenance et contrats IPC

`ExternalSources` utilise un seul worker daemon, sur le principe des jobs 3D
existants : résultats bornés, TTL 120 s, aucune lecture/écriture SQLite dans le
worker. Pas d'augmentation du timeout IPC de 8 s. Une requête annulée peut finir
son attente HTTP ; elle ne peut plus fournir un résultat ni écrire dans le staging.
Une nouvelle requête attend la libération du worker ; le parcours local reste libre.

Commandes strictes Python/Rust, permission Tauri dédiée :
`external_configuration`, `external_configure`, `external_search`,
`external_download`, `external_pdf`, `external_status`, `external_cancel`.
Toutes sont refusées en readonly/après restauration ; les opérations réseau et
leurs résultats exigent la préparation courante. Le frontend ne transmet ni
chemin, ni octets téléchargés, ni candidat modifiable : seulement des capacités
opaques, invalidées par préparation/configuration. Un téléchargement recontrôle
le candidat entier et ses empreintes avant le staging.

Le polling d'un résultat valide réutilise `PreparedFiles`. Aucun Asset ni Part
canonique à ce stade. Le commit transactionnel d'ingestion importe uniquement les
choix retenus et conserve origine KICAD_OFFICIAL/MANUFACTURER, commit + révision
ou URL, SHA-256, sélection du symbole et reçu durable. Le fichier multi-symboles
complet reste stocké ; l'aperçu analyse le symbole choisi et ses parents.
L'annulation n'efface que la préparation. Aucun import immédiat M9/M10 utilisé
pour produire un aperçu. Les blobs orphelins après rollback SQL suivent toujours
l'invariant M2/TECH-03, sans association partielle.

## Protections réseau

M9 conserve ses URLs GitLab officielles fixes, commits épinglés, contrôle blob
Git/SHA-256, refus des pointeurs LFS et redirections, limites de taille/délais.
M10 conserve HTTPS, domaines exacts, TLS, redirections refusées, signature PDF,
32 Mio réseau, attente 8 s et budget de lecture 20 s entre blocs. Son transport
refuse toutes les résolutions DNS non publiques/privées, y compris réponses mixtes
et adresses de transition IPv6. Il résout une fois, connecte une adresse numérique
vérifiée puis valide TLS sur le nom constructeur original ; aucun proxy système
ou seconde résolution susceptible de DNS rebinding.

Le wizard garde 16 Mio/fichier, 8 fichiers et 64 Mio/préparation, et ses aperçus
KiCad gardent 8 Mio. Un résultat M9/M10 plus volumineux est refusé explicitement,
sans augmenter les limites globales et sans fichier partiel. Le PDF doit aussi
avoir une fin de document. Ces contrôles ne certifient pas son contenu électronique.

Aucun appel au démarrage, en découverte locale, catalogue, validation, publication
ou restauration. Aucun secret, télémétrie, serveur, IA, SnapMagic ou mise à jour
automatique. Aucun changement du writer ou du nommage exporté.

## Vérifications automatisées

- Python complet avec FreeCAD : **636 passed** (31 cas supplémentaires).
- Ruff : conforme ; format : 264 fichiers conformes ; mypy : 190 modules conformes.
- Rust : **34 passed**, rustfmt conforme ; permission Tauri générée et contrôlée.
- Frontend TECH : **91 passed**, Svelte check sans erreur ni avertissement.
- Frontend UX : **12 passed**, Svelte check et build conformes.
- Sidecar et bundle Tauri macOS ARM64 reconstruits. Avertissement Vite habituel
  sur la taille des chunks ; aucune dépendance ajoutée.

Les nouveaux cas simulés couvrent opt-in, absence d'appels à la composition,
recherche explicite, commit/révision, substitution de candidat/hash, symbole
hérité complet, empreinte/STEP, consentement PDF, domaine refusé, destinations
privées et DNS rebinding, erreurs HTTP/timeout/redirection/taille, limites 32/16,
annulation en recherche/téléchargement, résultat retardé, refus inter-préparations,
absence d'Asset avant confirmation, import/provenance, readonly et forme IPC.
Les suites historiques exercent les interruptions transactionnelles, reçus,
STALE, sauvegarde/restauration, publication, installation et récupération.
Les tests frontend vérifient absence de requête au montage du contrôleur,
polling explicite, annulation tardive, erreur réseau sans retry et préservation
d'un choix local lorsqu'une ressource téléchargée est seulement examinée.

## Essais réseau publics réels

Exécution distincte des tests simulés, avec activation explicite :

- KiCad 9.0.0 `Timer:NE555D`, bibliothèque complète 183 213 octets,
  commit `a9012d8971ef2ea3243ffc9f19a5b4f153d8b334`.
- `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm`, 3 654 octets,
  commit `e515f1c3213317d436e492c8c06620ef4caca84e`.
- STEP correspondant, 253 807 octets,
  commit `d5db5cea003fe2b4b1c9b145f5fcbd5fdb48f8ca`.
- PDF public TI `https://www.ti.com/lit/ds/symlink/ne555.pdf`,
  2 258 813 octets, SHA-256
  `a3756e59fd06d0ba736edf9ffe71d99d2aae33fb7e49fedc86165a241179f4a6`.

Un dernier essai du **sidecar final embarqué** dans un workspace neuf confirme
les deux configurations initialement désactivées, recherche/téléchargement du
symbole NE555D et du PDF TI, staging puis annulation sans import canonique.

Ces essais utilisent les véritables adaptateurs M9/M10 et le réseau, pas les
fournisseurs simulés. Ils ne qualifient pas tous les tags/dépôts/constructeurs.

## Inspection native et limites

Paquet ARM64 réel, FR sombre en grande fenêtre et EN clair/FR sombre en fenêtre
réduite (~901 px). Défilement, boutons actifs/désactivés, focus, menus de sélection
et pied d'assistant vérifiés. Les longues URL des cartes reviennent maintenant à
la ligne : débordement horizontal constaté puis corrigé et revérifié nativement.
Les nouveaux libellés sont FR/EN ; les avertissements géométriques historiques
émis par le moteur restent parfois français, comme avant ce jalon.

- Sources désactivées initialement ; activation explicite des deux dans le seul
  workspace jetable. Paramètres enregistrés sans requête ; persistance vérifiée.
- Recherche et téléchargement réels du symbole NE555D : commit visible, aperçu
  temporaire, « Proposition non retenue », choix local conservé jusqu'à une
  nouvelle décision explicite. L'essai est annulé sans création canonique.
- Recherche/téléchargement réels de l'empreinte et du STEP SOIC-8 : dessin des
  huit pads et aperçu 3D interactif visibles. PDF TI : 39 pages, aperçu réel,
  consentement réinitialisé et aucune sélection automatique.
- Variante à référence distincte `NE555D — TECH06B`, nouveau package distinct,
  symbole local conservé, empreinte/STEP/PDF téléchargés explicitement retenus.
  Avant confirmation : 5 Parts / 1 Asset malgré trois fichiers en préparation.
  Après : 6 Parts / 4 Assets ; seuls trois Assets nouveaux, origines et hashes
  vérifiés, choix associés, reçu durable présent. Réouverture native confirmée.
- Dernier ajout téléchargé puis annulé : toujours 6 Parts / 4 Assets, staging vide.
- Copie figée du résultat lue par le sidecar embarqué : services externes refusés
  READ_ONLY et inventaire de fichiers inchangé. Sauvegarde complète créée et vérifiée.

Deux fermetures coopératives ont eu lieu pendant les manipulations du raccourci
clavier de sélection de texte de l'outil natif. Aucun ajout n'était confirmé :
comptages et staging contrôlés, puis relances explicites avec environnement
revérifié. La sélection native du texte a permis de poursuivre. Une indisponibilité
transitoire de fenêtre a ensuite été résolue par relecture du processus encore
actif ; aucune relance implicite. Les captures finales portent sur l'UI corrigée.

Toutes les données et configurations sont sous `local-data/tech06b`, copie séparée
de TECH-06A. Chaque lancement graphique a ses cinq chemins FabParts/KiCad vérifiés
dans le processus effectif avant Computer Use. Aucun KiCad graphique lancé.
Les **11 inventaires protégés** sont identiques : données personnelles, absence
initiale du workspace FabParts personnel, corpus TECH-05B, QUAL-01 et TECH-06A.
L'application de test est fermée au checkpoint.

Captures : [choix local conservé, FR](tech06b/downloaded-symbol-kept-local-fr.jpg),
[URL corrigée, FR sombre réduit](tech06b/downloaded-symbol-fr-dark-narrow.jpg),
[URL corrigée, EN clair réduit](tech06b/downloaded-symbol-en-light-narrow.jpg).

Le réseau PDF est direct : les environnements exigeant un proxy ne sont pas
pris en charge par ce transport durci. L'annulation révoque le résultat mais ne
tue pas un appel système DNS/HTTP déjà engagé ; le worker reste unique et le
reste de l'application utilisable. Pas de retry, cache réseau, téléchargement
récursif de modèle ou authentification. Une référence sans résultat peut rester
un brouillon local. Les trois étapes et les workflows existants sont conservés.

## Décision

**GO WITH CONDITIONS** — Les deux sources fonctionnent sur les ressources publiques
qualifiées, avec staging, consentement, provenance et import explicites. Aucun
problème d'intégrité/persistance connu dans les parcours vérifiés. Conditions :
limites 32/16/8 Mio, connexion PDF directe sans proxy, annulation non préemptive
d'une attente système, validation M5 toujours nécessaire et qualification native
limitée à macOS ARM64. Aucun contrat commercial ou autre plateforme revendiqué.

Commit et PR vers main ; **ne pas fusionner TECH-06B**. **STOP avant TECH-06C**.
