# ADR 0003 — Ingestion transactionnelle dans un sandbox writable

Date : 25 octobre 2026. Statut : retenu pour TECH-03.

## Contexte

L'[ADR 0002](0002-headless-readonly-sidecar.md) impose une copie figée et un
sidecar readonly. TECH-03 doit écrire sans affaiblir ce mode ni ouvrir la
production. Les services existants sauvegardent chaque opération séparément ;
une confirmation doit réunir plusieurs opérations et résister à une réponse IPC
perdue. SQLite et l'Asset Store n'ont pas de transaction commune.

## Décision

Deux compositions explicites au point d'entrée headless :

- readonly conserve URI immutable, query_only, authorizer et absence de migration ;
- writable ouvre SQLite ordinaire dans un sandbox neuf marqué, de schéma connu,
  choisi par l'hôte, avec verrou exclusif et sauvegarde préalable.

Le sidecar n'effectue aucune migration. Un CLI d'administration prépare ou restaure
un nouveau dossier. La restauration conserve sa source. Les chemins liés à la
production macOS et aux copies readonly sont refusés. Les marqueurs ne sont pas
une isolation contre un utilisateur local ayant déjà les mêmes droits disque.

Un port de transaction d'ingestion fournit des adaptateurs Catalogue et
Documentation partageant une Session SQLAlchemy. Les adaptateurs empruntés
flushent ; seul le coordinateur committe sous BEGIN IMMEDIATE. Le domaine et
les règles des cas d'usage existants restent inchangés. Les lectures writable
emploient le même moteur SQLite ordinaire, jamais une connexion immutable.

La migration additive 0008 ajoute uniquement les reçus : UUID d'opération,
SHA-256 de requête et FK Part. Le reçu et les modifications métier sont engagés
ensemble. Rejeu exact : même résultat ; contenu différent : refus. Le downgrade
refuse de supprimer des reçus existants. Le frontend peut consulter le résultat
après timeout/redémarrage avant toute nouvelle décision.

Rust acquiert les fichiers par sélecteur natif, contrôle l'ouverture et la
stabilité, puis transmet des blocs bornés. Python détient une préparation
temporaire bornée et les candidats autorisés. La WebView ne possède ni accès
filesystem général ni commande de transfert arbitraire ni choix du dossier writable.

La confirmation réutilise AssetImports et LocalAssetStore. Les blobs sont
publiés avant commit SQL ; un échec peut conserver des octets orphelins mais
jamais une confirmation partielle. Aucun blob canonique n'est supprimé.
L'annulation ne supprime que le staging de sa préparation et ses capacités.

## Alternatives écartées

Retirer les protections du mode readonly rendrait la frontière implicite et
les lectures immutable incohérentes. Réimplémenter un catalogue Rust/TypeScript
dupliquerait les invariants. Enchaîner les commits unitaires laisserait des états
partiels. Une transaction distribuée ou une nouvelle architecture de journal
dépasserait le besoin ; le reçu SQL et l'ordre existant des blobs suffisent ici.

## Conséquences

La production reste hors périmètre. Les sauvegardes et les blobs orphelins peuvent
croître et ne sont pas purgés automatiquement. Une préparation non enregistrée
n'est pas durable ; un DRAFT et son reçu le sont. Les packages partagés existants
ne sont pas modifiés par le wizard. Le marqueur, le verrou POSIX et la configuration
hôte ne sont qualifiés que sur macOS ARM64.

Les erreurs et interruptions réelles avant/après commit, la restauration,
le readonly et les contrôles natifs sont détaillés dans le
[rapport TECH-03](../FABPARTS_2_TECH_03.md).
