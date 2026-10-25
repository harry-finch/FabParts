# ADR 0004 — Workspace personnel et sauvegardes vérifiées

Date : 26 octobre 2026. Statut : retenu pour TECH-04A.

## Décision

Le lancement normal du host ouvre un workspace personnel neuf sous le dossier
système FabParts. Aucun catalogue KiPart Manager n'est découvert ou importé.
Le host conserve l'autorité sur le chemin writable ; la WebView ne peut pas le
choisir. Les compositions sandbox et readonly restent explicites et inchangées.

Ce mode étend l'ADR 0003 : **seul le workspace personnel** initialise Alembic ou
exécute la migration additive qualifiée 0007 → 0008. Le readonly ne migre jamais ;
le sandbox exige toujours un schéma courant préparé explicitement. Aucun nouveau
schéma ni changement des règles métier.

Un verrou POSIX sur le dossier personnel couvre toute la session, y compris les
générations restaurées. `active.json` désigne une génération UUID sous
`workspaces/`. Chaque génération porte un marqueur propre. Les symlinks et liens
physiques extérieurs sont refusés. Ces protections ne constituent pas une barrière
contre un utilisateur malveillant disposant déjà des mêmes droits système.

La sauvegarde partagée avec TECH-03 utilise `sqlite3.backup`, copie l'Asset Store,
la configuration et les publications avec leurs dépendances, puis vérifie le
manifeste SHA-256, SQLite, les blobs référencés et les publications. Seul un dossier
entièrement vérifié est renommé de `.partial-UUID` en UUID. Les fichiers temporaires
et index reconstruisibles sont exclus. Les anciens backups et blobs sont conservés.

Avant migration, un backup complet doit être créé et vérifié. Un schéma inconnu
ou futur est refusé avant toute migration. Le démarrage courant ne crée pas de
backup systématique.

Une restauration confirme un identifiant opaque issu d'un sélecteur natif. Le
backend revérifie la source, sauvegarde l'actif, restaure dans une nouvelle
génération privée puis remplace atomiquement le pointeur actif. L'ancien workspace
et sa sauvegarde restent présents. Les écritures sont suspendues jusqu'au
redémarrage explicite du moteur. Une interruption antérieure au remplacement du
pointeur laisse l'ancien actif ; après remplacement, le nouveau est complet.

## Conséquences

Pas de profils, de purge automatique, de synchronisation ni de sauvegarde réseau.
Les snapshots sont des dossiers portables vérifiés, pas des archives ZIP. Il faut
assez d'espace pour le backup de sécurité et la nouvelle génération. Les dossiers
partiels sont conservés et refusés par le vérificateur. La reprise d'un workspace
qui ne peut plus démarrer reste une opération d'administration explicite ; ce
jalon ne fournit pas d'écran de récupération indépendant du moteur.

Qualification native : macOS ARM64. Windows et Linux ne sont pas qualifiés.
