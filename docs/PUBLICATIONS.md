# Publications versionnées M7

M7 engage un instantané d'une collection qualifiée. La construction ponctuelle M6
reste disponible ; elle n'ajoute pas de version. Le catalogue SQLite et les assets
courants restent les sources de vérité de travail. Les manifests et copies retenues
font autorité sur les états historiques, conformément à l'architecture.

## Utilisation

1. Choisir les ressources de la collection et effectuer sa validation M5.
   ERROR, STALE ou WARNING non accepté bloquent une nouvelle publication.
2. Ouvrir **Publications**, choisir la collection puis le numéro proposé.
   Les versions sont des entiers 1–999999 propres à chaque UUID de collection.
   Des trous sont autorisés ; aucun numéro occupé ne peut être réutilisé.
3. Cliquer **Publier une version**. Une nouvelle version conserve les précédentes.
4. Sélectionner une version pour **Vérifier les hashes** ou **Reconstruire cette
   version** dans un nouveau dossier hors données et bibliothèques sources.
   La destination doit avoir un parent existant ; tout dossier existant est refusé.

Le filtre « Toutes les publications » permet de consulter l'historique complet.
Il ne permet pas de publier sans choisir une collection. « PUBLISHED » signifie que
le manifest correspond à son marqueur COMMIT ; PASS après vérification indique
l'intégrité des fichiers à cet instant, pas une nouvelle certification M5/CAO.

## Format et associations figées

```text
<data>/publications/<UUID_collection>/v000001/
  manifest.json
  COMMIT                   # SHA-256 du manifest, installé en dernier
  inputs/<SHA256><extension>
  artifacts/               # sorties autonomes du builder M6
```

Le JSON canonique UTF-8 utilise le schéma 1 et le builder `M6-1`.
Il décrit UUID/nom de collection, version, horodatage UTC, Parts avec UUID/nom,
association au Package et choix par rôle, UUID d'asset ou référence officielle
portable, origine, descripteur du fichier, hashes et tailles. Il conserve aussi
l'empreinte et les résultats structurés M5, le ruleset et l'acceptation des WARNING.
Les messages libres M5 et références/source arbitraires de poste sont omis afin
de ne pas exporter de chemins d'installation. Les UUID/origines, noms de fichiers
et références officielles préservent la traçabilité des ressources retenues.

L'instantané couvre les associations **choisies pour la construction**, pas une
copie intégrale du catalogue, des stocks ou des assets non choisis. Les noms et
UUID nécessaires au writer sont figés. Les inventaires ne conditionnent pas ces
versions. Aucun état de Part n'est modifié par la publication.

Chaque dépendance est copiée et contrôlée avant engagement. Les copies historiques
sont gérées sous `inputs/`, séparées des blobs courants ; aucune nouvelle fiche
Asset ni provenance USER_PROVIDED artificielle n'est créée pour les ressources
officielles. Les symboles officiels conservent leur fichier source complet afin
de garder les parents d'héritage nécessaires. Seuls les fichiers choisis sont
retenus, jamais toute l'installation KiCad. Les modèles 3D et PDF sélectionnés
sont également conservés. Les mêmes octets/extension sont dédupliqués à l'intérieur
d'une version sans fusionner les identités. Il n'y a pas de déduplication entre
versions ou de purge automatique.

Le manifest n'utilise aucun chemin d'installation. Les artefacts conservent les
liens `${KIPRJMOD}` de M6. Les octets bruts retenus ne sont pas réécrits : une source
originale peut contenir ses propres métadonnées ou indices de chemin, qui ne sont
pas utilisés pour résoudre les dépendances de reconstruction.

## Garantie de reconstruction

Avec un manifest engagé intact, ses dépendances retenues intactes et un builder
compatible `M6-1`, M7 régénère les **mêmes fichiers et octets** que ceux identifiés
par l'inventaire historique SHA-256/taille. Noms de fichiers, symboles, footprints,
liens, modèles, datasheets et textes M6 sont comparés. Toute différence bloque la
sortie ; le code ne réécrit jamais le manifest pour accepter une différence.

La reconstruction ne lit ni catalogue courant, ni rapports courants, ni blobs
courants, ni fichiers officiels. L'adaptateur consulte seulement la configuration
locale de dossiers pour empêcher une destination dans les bibliothèques sources.
Une mise à jour ou disparition des fichiers KiCad après engagement n'affecte pas
la reconstruction. Avant une nouvelle publication, les références actuelles doivent
à nouveau être disponibles et qualifiées ; une modification ne remplace jamais
silencieusement le choix précédent.

Les artefacts historiques sont vérifiés par l'action d'intégrité, mais ne sont
pas requis comme source de reconstruction. Si seuls ces artefacts sont endommagés,
un dossier neuf peut être régénéré depuis `inputs/` ; la version historique n'est
pas réparée ou modifiée automatiquement. Un input ou manifest perdu/corrompu
nécessite une sauvegarde : la reconstruction n'essaie pas de lui substituer une
version courante de hash différent.

La garantie n'inclut pas les timestamps, permissions ou ordre filesystem, ni une
compatibilité avec toutes les futures versions du logiciel ou de KiCad. Un futur
writer doit conserver un moteur compatible ou refuser clairement cette version.
Le test simule un changement d'octets du writer et vérifie ce refus. Les limites
sémantiques M5 et de formats M6 restent applicables.

## Engagement, échecs et sauvegarde

La version est préparée dans un staging `.pending-*` voisin. Les octets sont
copiés, les artefacts construits/contrôlés et le plan/rapport courant revérifiés.
Le dossier final est réservé exclusivement ; les fichiers sont installés par
liens physiques exclusifs depuis le staging, sans partager les sources courantes.
Un dernier contrôle précède l'installation exclusive de COMMIT.

Les lecteurs n'exposent que les dossiers avec COMMIT correspondant au hash du
manifest et aux identités annoncées. Sans COMMIT, un dossier est incomplet et
ignoré. Un COMMIT/manifest incohérent provoque une erreur explicite, jamais une
présentation comme version valide. La vérification complète des dépendances et
artefacts est une action distincte : la liste ne prétend pas effectuer ces lectures
coûteuses à chaque rafraîchissement.

Les écritures sont flush/fsync et les répertoires synchronisés sur POSIX. Les
exceptions nettoient les fichiers installés par l'opération ; les ajouts étrangers
inattendus sont conservés. Un arrêt brutal peut laisser un staging ou un dossier
sans COMMIT : aucune reprise/purge automatique ni réutilisation de son numéro.
Choisir un autre numéro ; ne pas traiter ce dossier comme publication.
Une concurrence sur un même numéro a un seul gagnant, sans écrasement.

L'engagement est une frontière filesystem ; SQLite n'est pas réécrit. Un changement
courant après le dernier contrôle ne modifie pas l'instantané déjà capturé.
L'immutabilité est assurée par les API, pas par une signature cryptographique ou
une protection contre toute modification externe. Les hashes détectent les
corruptions accidentelles ; les publications ne sont pas des archives importables.

Sauvegarder ensemble `database/`, `assets/`, `publications/` et la configuration
après fermeture. Conserver également une version du logiciel compatible avec le
builder historique. Les opérations restent synchrones ; l'inspection native M7
est réalisée sur macOS, sans qualification Windows/Linux ou coupure électrique
réelle. Aucun réseau, serveur, IA, nouveau package ou exécutable KiCad n'est requis.
Le filesystem doit supporter les liens physiques exclusifs.

M8 (ZIP `.kiparts`, transfert/import) reste non démarrée.
