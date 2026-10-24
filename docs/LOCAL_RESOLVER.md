# Resolver local — M4

## Utilisation

Dans **Composants** ou **Packages**, sélectionner une fiche puis cliquer
**Résoudre les ressources locales**. Choisir le rôle, ajuster la recherche et
examiner les candidats. Aucun candidat n'est présélectionné ou enregistré
par une recherche.

Les symboles et datasheets appartiennent au choix de la Part. Les footprints et
modèles 3D appartiennent au choix de son Package. Depuis une Part ayant un Package,
les quatre rôles sont proposés ; sans Package, seuls symbole et datasheet le sont.
Un choix mécanique sur un Package partagé concerne toutes les Parts qui y font
référence ; le dialogue l'indique explicitement.

Les candidats sont regroupés dans cet ordre :

1. Assets du catalogue d'origine `USER_PROVIDED`.
2. Autres assets du catalogue géré, avec leur provenance propre.
3. Références de l'index officiel KiCad local.

La recherche porte sur nom, source/référence et nom du fichier original des assets,
et sur les métadonnées de l'index pour KiCad. Les assets déjà associés à la fiche
restent visibles pour le rôle demandé même s'ils ne correspondent pas au texte.
La recherche est une sous-chaîne insensible à la casse, pas une estimation de
compatibilité électrique ou mécanique. Les candidats officiels sont limités aux
200 premiers résultats M3 ; les résultats gérés ne sont pas limités.

UUID, provenance et SHA-256 sont présentés. Deux assets distincts ou un asset et
une référence officielle restent des candidats différents, même avec le même
hash. Les assets sans fichier, manquants ou corrompus sont visibles avec la raison
de leur indisponibilité ; ils ne sont pas sélectionnables. Une référence officielle
est issue du cache ; sa disponibilité et son hash sont vérifiés au choix.

Sélectionner une ligne puis **Choisir le candidat sélectionné** enregistre le
choix. Pour changer un choix déjà présent, cocher **Je confirme le remplacement du
choix actuel**. La confirmation est réinitialisée après recherche/enregistrement.
Changer le choix conserve les fichiers et associations antérieurs. Une sélection
concurrente ou un candidat modifié exige une nouvelle recherche.

Le dialogue affiche le choix actuel même s'il n'est plus dans les résultats.
Un résultat vide, un index absent/corrompu ou une erreur ne supprime pas ce choix.
Les recherches locales et sélections d'assets gérés restent utilisables sans
installation KiCad ; les signalements de l'index sont affichés séparément.
Les datasheets sont recherchées dans le catalogue seulement.

## Persistance et protection

Une sélection existe au plus une fois par propriétaire/rôle. La table
`resource_choices`, ajoutée par Alembic `0003_resource_choices`, ne modifie pas les
associations M1/M2 et ne déduit aucun choix des données anciennes.

- Choix géré : UUID de l'Asset, avec clé étrangère vers le catalogue. Si nécessaire,
  l'association à la Part/au Package est ajoutée dans la même transaction.
- Choix officiel : instantané JSON de `KiCadReference`, incluant identité portable,
  chemin relatif, provenance implicite officielle, hash, version et métadonnées.
  Aucun Asset, blob ou copie officielle n'est créé. Les racines propres au poste
  restent dans la configuration M3.

Les choix officiels survivent à la suppression/reconstruction du cache. Ils ne
suivent pas automatiquement un nouveau hash de bibliothèque. Leurs octets restent
externes ; une référence persistée n'est pas une garantie de disponibilité.

Les écritures catalogue/sélection sont sérialisées par `BEGIN IMMEDIATE` sur SQLite.
La sélection compare le choix attendu **dans** la transaction, et ajoute
l'association gérée avant commit. Un échec annule l'ensemble. Les associations
sélectionnées ne peuvent pas être retirées par l'éditeur de métadonnées ; le type
d'un asset sélectionné ne peut pas être modifié. Les fichiers M2 restent immuables.
Après un remplacement explicite, une ancienne association n'est plus protégée par
ce choix et peut être retirée volontairement dans l'éditeur.

La vérification des octets se fait avant la transaction : M4 n'introduit pas de
transaction filesystem/base commune. Une modification externe après le contrôle
reste possible ; M5 et les étapes de publication devront vérifier leurs entrées.

## Limites

Aucune génération, publication, validation sémantique ni nouveau cycle d'état de
Part. Les choix et assets restent UNCHECKED. Le rôle 3D est choisi sur le Package ;
les liens fins footprint/modèle et transformations mécaniques relèvent des étapes
suivantes. Un asset SYMBOL géré désigne le fichier importé ; la sélection d’une
entrée interne d’une bibliothèque utilisateur contenant plusieurs symboles n’est
pas proposée en M4. Le resolver ne résout pas l’héritage des symboles et ne charge pas de
bibliothèque distante.

Les recherches et vérifications de fichiers sont synchrones dans ce dialogue.
Une liste contenant de gros fichiers peut prendre du temps. Il n'y a pas de
suppression d'un choix dans M4 ; un choix se change explicitement par un autre.
Il n'y a pas de surveillance continue des bibliothèques officielles ou du store.
Rechercher à nouveau après changement de candidat et reconstruire l'index après
mise à jour KiCad. Les limites de [KICAD_INDEX.md](KICAD_INDEX.md) restent applicables.
