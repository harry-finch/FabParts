# .kiparts — transfert portable M8

Une archive transporte **une version publiée** et ses dépendances. Depuis
**Publications**, sélectionner une version puis **Exporter cette version en
.kiparts…**. Le fichier cible doit être nouveau et hors des données et bibliothèques
sources. L'export vérifie la version, ses sources et ses sorties avant de rendre
l'archive disponible.

Sur l'autre machine, **Importer un .kiparts…** ouvre un aperçu avec bibliothèque,
version, nombres de composants/packages/ressources et conflits éventuels.
**Importer sans remplacer** engage l'import ; **Fermer l’aperçu** revient à
l'historique. L'import relit l'archive et les conflits au moment de l'engagement.
Après import, **Reconstruire cette version** produit une copie KiCad autonome dans
un nouveau dossier. Les tables sont des tables de projet utilisant KIPRJMOD ;
suivre le fichier UTILISATION.txt et conserver les tables préexistantes du projet.

## Format 1

ZIP non chiffré, entrées fichiers ordinaires uniquement, compression Stored ou
Deflate. Racine :

- manifest.json : format "kiparts", schema 1, hash du manifest historique,
  inventaire relatif SHA-256/taille, libellés complémentaires et provenance portable ;
- publication/manifest.json et publication/COMMIT : octets M7 inchangés ;
- publication/inputs : dépendances figées ;
- publication/artifacts : sorties KiCad de cette version.

Limites actuelles : 10 000 fichiers de publication, 1 Gio décompressé pour
l'archive complète, 64 Mio par manifest. Les doublons ZIP/JSON, liens symboliques,
fichiers spéciaux, chemins absolus, segments parents, antislashs, deux-points,
noms nuls, fichiers supplémentaires/manquants et formats inconnus sont refusés
avant import. L'extraction utilise un dossier temporaire privé, jamais extractall.

Chaque fichier est relu et hashé. Le manifest engagé, les dépendances et les
associations sont contrôlés. Les artefacts sont reconstruits temporairement depuis
les sources figées et doivent être identiques aux sorties annoncées. L'intégrité
SHA-256 assure la cohérence ; le format ne comporte pas de signature d'auteur.

## Projection dans le catalogue

La publication conserve à l'identique UUID, numéro/date de version, origine,
hashes, qualification historique et choix officiels. Le catalogue courant reçoit
les composants et packages nécessaires, leurs associations et leurs choix de
ressources. Les assets déjà gérés gardent leurs UUID et descripteurs de fichier.

Une référence officielle est matérialisée comme asset local avec origine
KICAD_OFFICIAL et identité source portable. Son UUID est déterministe, dérivé de
la clé de référence et du hash. Le fichier original complet est conservé : pour
un symbole, AssetFile.symbol_name désigne l'entrée, y compris son héritage.
La migration 0005_symbol_entry conserve les fichiers existants avec une entrée
vide ; un downgrade est refusé si une sélection serait perdue.

Les libellés des packages et assets encore disponibles peuvent être repris du
catalogue lors de l'export. Sinon des noms de secours sont calculés. Les URLs de
provenance, identités officielles et informations simples sont conservées ; un
chemin source local est représenté par local-file suivi du nom original.
Aucune installation source n'est nécessaire à l'import, à la validation ou à la
reconstruction.

Ce transfert n'est pas une sauvegarde du catalogue courant : descriptions,
états de travail, associations non sélectionnées, autres collections, stocks,
inventaires, emplacements et configuration du poste ne font pas partie de la
version publiée. Les nouveaux composants arrivent en DRAFT et les rapports de
validation courants ne sont pas importés. Revalider avant une nouvelle publication.
Un objet local identique réutilisé conserve ses descriptions, état et rapports.

## Conflits et engagement

La politique M8 est **refuser tout conflit**, sans fusion ni remplacement :

- un UUID existant doit correspondre aux données transférées : nom, type/origine,
  fichier/entrée de symbole, associations, package, membres et choix ;
- la provenance portable disponible doit correspondre ; les chemins du poste ne
  constituent pas une différence de contenu ;
- un nom de bibliothèque déjà utilisé par un autre UUID bloque l'import ;
- une version existante doit avoir le même manifest et passer la vérification.

Réimporter des données identiques est idempotent. Une modification locale depuis
l'aperçu est détectée lors du second contrôle, sous BEGIN IMMEDIATE.

Les blobs sont copiés et vérifiés avant les associations SQLite. La projection
entière utilise une seule transaction ; la version est installée exclusivement
avec COMMIT en dernier. Une exception annule la transaction et retire uniquement
les fichiers de version possédés par cet import. Les versions préexistantes restent
intactes. Des blobs dédupliqués sans association peuvent rester après un échec ;
ils ne sont jamais présentés comme composants importés.

SQLite et fichiers n'ont pas de transaction distribuée : une interruption brutale
dans la fenêtre entre engagement du manifest et commit SQLite peut laisser une
version intacte sans projection. Réimporter la même archive rétablit la projection.
Une interruption antérieure peut laisser un dossier sans COMMIT, invisible dans
l'historique mais bloquant la réutilisation de ce numéro. Aucun succès n'est annoncé
avant la fin des vérifications et du commit.

Les opérations M8 sont locales et synchrones ; une archive importante peut
immobiliser momentanément l'interface. Aucun réseau, fournisseur IA ou serveur
n'intervient.
