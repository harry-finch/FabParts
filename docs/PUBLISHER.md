# Construction KiCad M6

M6 construit une bibliothèque depuis une Collection qualifiée par M5. Les sorties
sont des artefacts de l'état courant ; elles ne remplacent ni SQLite ni l'Asset Store.
M6 ne crée aucune version publiée, manifest M7 ou archive `.kiparts` M8.

## Utilisation

1. Choisir explicitement les ressources avec le resolver : symbole sur Part,
   footprint et éventuel modèle 3D sur Package, datasheet facultative sur Part.
2. Valider la Collection, examiner et accepter ses éventuels WARNING. Un rapport
   de Part seul ne qualifie pas sa Collection. ERROR, STALE ou absence de rapport
   bloquent la construction.
3. Dans **Collections**, sélectionner la collection puis **Construire une
   bibliothèque KiCad** (bouton **Construire pour KiCad**). Choisir un nouveau dossier de sortie dont le parent
   existe, hors des données locales et bibliothèques sources.
4. Cliquer sur **Construire la bibliothèque**, puis consulter `UTILISATION.txt`.

LabParts et PersonalParts sont construits séparément ; chaque collection a son
nickname propre. Toute destination existante, même vide ou symlink, est refusée.
Pour reconstruire, choisir un nouveau dossier. M6 n'écrase aucun résultat précédent
et ne change pas le catalogue, les choix ou le statut global des assets.

## Mode de copie et références

M6 fournit **un seul mode : copie autonome des ressources explicitement choisies**.
Les références officielles servent à retrouver et vérifier leurs sources locales ;
elles ne restent pas des dépendances d'installation dans les sorties. Seules les
ressources nécessaires sont copiées dans le dossier de construction, jamais dans
l'Asset Store. Les symboles choisis sont extraits avec leurs parents d'héritage.
Les fichiers officiels et utilisateur restent en lecture seule.

Un mode qui laisserait les footprints/modèles dépendre de l'installation KiCad
n'est pas proposé en M6. La trace conserve identité, origine et hash source dans
`SOURCES.txt`, sans chemin d'installation ni référence/source arbitraire susceptible
de contenir un chemin du poste. Ce fichier est une liste de traçabilité, sans hashes
des sorties, version publiée ou garantie d'instantané historique.

Sorties :

```text
<destination>/
  KPM_<nom_ASCII>_<UUID_collection>.kicad_sym
  KPM_<nom_ASCII>_<UUID_collection>.pretty/
    F_<UUID_package>.kicad_mod
  KPM_<nom_ASCII>_<UUID_collection>.3dshapes/  # si modèles choisis
    <SHA256_source>.step|.stp|.wrl
  datasheets/                              # si PDF choisis
    <SHA256_source>.pdf
  sym-lib-table
  fp-lib-table
  UTILISATION.txt
  SOURCES.txt
```

Le préfixe ASCII et l'UUID complet évitent les collisions de noms et les caractères
non portables. Les Parts deviennent `P_<UUID_part>`, avec leur nom catalogue dans
le champ Value et la table lisible de `UTILISATION.txt`. Un Package partagé ne produit
qu'un footprint par collection. Des fichiers identiques de modèle/PDF sont copiés
une seule fois par hash et extension, sans fusion de leurs identités catalogue.

Les parents de symbole nécessaires portent `P_<UUID_part>__base_<rang>` ; ils
restent des entrées techniques visibles dans KiCad. Les références `extends` et
noms d'unités sont réécrits ensemble. Les propriétés, graphiques, pins et autres
champs source sont conservés, sauf noms, Value du composant, liens Footprint et
Datasheet réécrits. Un PDF non choisi ne devient pas une dépendance implicite :
le champ Datasheet exporté reste vide.

## Liens et compatibilité

Le symbole pointe sur `<nickname>:F_<UUID_package>`. Les tables sont des tables de
**projet**, avec URIs `${KIPRJMOD}/...`. Les modèles et datasheets utilisent également
`${KIPRJMOD}`. Placer les sorties à la racine du projet KiCad, ou adapter explicitement
les URIs relatives lors de leur intégration. Ne pas remplacer une table existante :
ajouter les entrées fournies à ses tables. M6 ne modifie aucune table globale.
Les tables séparées des deux collections peuvent être regroupées dans un projet
avec leurs nicknames distincts.

Un modèle choisi exige au moins un lien de modèle déjà présent dans le footprint,
avec un nom de fichier identique. Toutes les transformations correspondantes sont
conservées : offset/at, rotation et échelle. Sans modèle choisi, un footprint déclarant
un lien 3D est refusé. Un autre nom ou plusieurs dépendances distinctes sont refusés,
y compris après acceptation des WARNING M5. Le modèle M4 ne peut représenter qu'un
choix 3D sur Package ; M6 ne devine pas les autres ressources ou leur placement.
Choisir une ressource compatible ou importer un nouveau footprint explicitement
édité avant de revalider ; aucun fichier existant n'est modifié automatiquement.

Les dépendances de simulation déclarées `Sim.Library`/`Spice_Lib_File` non vides
sont refusées. Les modèles WRL comportant le mot `url`, ainsi que les déclarations
STEP `EXTERNALLY_DEFINED*`, `EXTERNAL_SOURCE*` ou `EXTERNAL_FILE*`, sont refusés
conservativement, sans résolution de dépendances transverses. Cette détection n'est
pas une validation CAO exhaustive et peut refuser une occurrence dans un commentaire.

Les entrées KiCad suivent les bornes 6–10 du [guide d'index](KICAD_INDEX.md).
La bibliothèque de symboles prend la version de format la plus récente de ses
sources ; les footprints gardent leur version. **Aucun downgrade de format n'est
réalisé** : des sources KiCad 10 nécessitent un lecteur compatible KiCad 10.
Les anciennes versions source ne sont pas artificiellement présentées comme
compatibles avec un lecteur plus ancien que leur format. Les racines de bibliothèque
à extensions non prises en charge sont refusées au lieu de perdre leurs métadonnées.
L'essai natif de lecture de cette milestone a été effectué avec KiCad 10.0.7.

Le writer préserve chaînes UTF-8, guillemets, échappements et ordre des atomes/enfants.
La sortie est sérialisée déterministement et reparsée ; héritage, pins/pads et liens
sont contrôlés avant exposition. Il transforme les ressources choisies et ne génère
aucun nouveau dessin de symbole, footprint ou géométrie 3D.

## Reconstruction, staging et limites

À catalogue, choix, octets source et code de construction identiques, deux dossiers
neufs ont le même contenu octet pour octet. Horodatages filesystem et emplacement
ne participent pas aux fichiers produits. Les noms catalogue et le code du builder
peuvent changer les octets ; il ne s'agit pas de la reconstruction d'une version
historique immuable M7.

Le builder capture des copies vérifiées par hash, construit dans un dossier
temporaire voisin de la destination et contrôle les liens. L'application revérifie
la qualification et le plan avant installation, puis après installation. Une
modification pertinente bloque le résultat et nettoie les sorties de cette opération.
L'ancien rapport reste conservé et devient STALE selon M5.

Le dossier final est réservé par création exclusive. Les fichiers sont installés
par liens physiques exclusifs depuis les copies temporaires, sans partager les
blobs source. Un marqueur `BUILDING` signifie **construction incomplète** ; il est
retiré seulement après les contrôles finaux. Un arrêt brutal peut laisser ce dossier
ou un staging `.kipart-build-*` ; ne pas utiliser une sortie marquée BUILDING et
choisir un autre dossier au prochain essai. Les erreurs normales nettoient leurs
propres sorties, en conservant les ajouts étrangers inattendus. Ce protocole n'est
pas un engagement atomique de publication versionnée ; M7 reste à réaliser.

Les lectures source et SQLite ne forment pas une transaction atomique commune.
Une modification après le dernier contrôle reste possible. Les contrôles M5 demeurent
partiels : ni la géométrie/les unités 3D, ni le contenu PDF, ni toutes les règles
électriques/DRC ne sont certifiés. Un WARNING accepté n'étend pas leur couverture.

Les opérations sont synchrones et peuvent ralentir l'UI pour une grande collection.
Un volume ne supportant pas les liens physiques signale une erreur sans écrasement.
Aucun exécutable KiCad, réseau, serveur ou IA n'est nécessaire à la construction
elle-même. Les références officielles exigent les fichiers source locaux ; leur
cache d'index peut être supprimé après sélection. Les vérifications avec KiCad CLI
sont des essais d'intégration distincts, pas une dépendance du cœur.

Documentation primaire : [formats KiCad](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/)
et [tables et chemins de projet](https://docs.kicad.org/9.0/is/getting_started_in_kicad/getting_started_in_kicad.html).

M7 ajoute un historique distinct dans **Publications**, décrit dans [PUBLICATIONS.md](PUBLICATIONS.md).
