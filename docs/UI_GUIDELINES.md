# Conventions UI — Professional Workshop

Référence visuelle : [professional-workshop-ui](../.agents/skills/professional-workshop-ui/SKILL.md),
complétée par la skill PySide du projet. Ce guide décrit l’implémentation actuelle,
pas une nouvelle couche de design. Les règles métier restent inchangées.

## Shell et navigation

Identité visible : **FabParts** — **Electronic component manager**. Barre supérieure
neutre #191919, filet ambre de 2 px, nom clair, logo QFP conservé et accès Paramètres.
Barre de statut inférieure : fonctionnement local et version. Les identifiants
Python, le dossier de données historique et le format `.kiparts` restent stables.
Les boutons secondaires utilisent #292929 ; les champs sont plus sombres que les
panneaux. Sections plates séparées par un trait fin ; menus et recherches suivent
le même thème central.

Six espaces orientés tâches : **Composants**, **Inventaire**, **Bibliothèques**,
**KiCad local**, **Publications**, **Paramètres**. Une sidebar compacte de 176 px
précède le workspace. Icônes Lucide de 16 px, logo QFP approuvé de 32 px dans une barre produit horizontale,
sélection ambre atténuée. Aucun écran par table du domaine ajouté.

Composants est l’entrée principale. Onglets Catalogue / Packages partagés /
Fichiers & ressources / Documentation selon services disponibles. Inventaire
regroupe Quantités / Inventaires / Emplacements. KiCad garde Installation locale
et Officiel distant si ces services sont composés. Les services absents ne créent
pas d’écrans fictifs. Aucun réseau ni fournisseur n’est requis au démarrage.

## Thème, densité et surfaces

`ui/theme.py` centralise palette Fusion sombre, QSS, couleurs de rendu et espacements.
Le fond #1e1e1e, les panneaux #232323 et champs #171717 établissent la hiérarchie.
Le texte principal est #e3e3e3 ; le secondaire #ababab. Pas de noir pur, gradients,
ombres décoratives, grands aplats sémantiques ou QSS propres à chaque écran.

Les accents interactifs reprennent l’identité FabParts. Les valeurs restent dans
`COLORS` de `ui/theme.py`, utilisées à la fois par QSS et QPalette :

| Token | Valeur | Usage |
| --- | --- | --- |
| ACCENT / PRIMARY / IDENTITY | `#E8B954` | Navigation active, onglets, focus, liens, actions principales, filet de marque |
| PRIMARY_HOVER | `#F0C66A` | Survol des primaires, bord des secondaires survolés |
| PRIMARY_PRESSED | `#DCA844` | Primaire pressé, lien déjà visité |
| PRIMARY_TEXT | `#202226` | Texte et icône sur bouton jaune rempli |
| SELECTION | `#3B3425` | Fond des lignes, texte sélectionné, contrôles cochés |
| INFO | `#579edb` | Trait des messages informatifs, indépendant de l’identité |

Les surfaces graphite et le hover neutre des commandes ordinaires sont conservés.
Un primaire désactivé reprend PANEL / DISABLED / LINE, y compris au survol ; le
focus d’un bouton rempli utilise un bord sombre, celui des autres contrôles un bord
ambre. Les onglets gardent leur soulignement, la sidebar son trait latéral et les
lignes leur fond discret : aucun de ces états n’est un WARNING. Les coches restent
claires sur fond sombre. Une icône sur bouton rempli peut être teintée via
`icons.icon(color=...)` avec PRIMARY_TEXT ; les autres Lucide restent neutres.

Contrastes : texte sombre sur primaire 8,72:1, hover 9,85:1, pressé 7,38:1 ; texte
clair sur SELECTION 9,75:1. Tests dédiés aux textes et aux accents de focus.

Tokens : XS=4, S=8, M=12, L=16, XL=24. Contrôles usuels proches de 28–32 px ; lignes
du catalogue 32 px. Les listes utilisent un retrait de 3 px pour préserver le
cadre de sélection. Rayons de 2–3 px ; espaces de panneau 8–12 px ; séparation
par espacement et contraste subtil. Les anciennes grandes cartes blanches sont
remplacées par des sections plates. Le contenu des inspecteurs reste aligné en haut.

Typographie système : corps 12 px, titre de page 18, titre d’objet 13, section
11 en capitales sobres, marque 16. Les informations techniques ne doivent pas
concurrencer les valeurs utiles. Les libellés de propriétés ont une largeur
lisible ; les valeurs longues se replient ou sont accessibles par infobulle.

## Primitives réutilisables

| Primitive | Convention |
| --- | --- |
| PageLayout | Marges L, espacement M ; layouts Qt redimensionnables |
| PageHeader | Titre compact, courte description ; longues explications repliables |
| SectionCard | Section plate, titre discret, contenu aligné en haut |
| ScrollPanel | Inspecteur/champs défilants, sans cadre supplémentaire |
| Disclosure | Commande discrète avec chevron, propriétés secondaires repliées |
| DetailText | Texte brut sélectionnable, replis des hashes, sans HTML implicite |
| SearchBar | Recherche effaçable avec nom accessible |
| EmptyState | État vide concis, prochain geste ou action réelle |
| StatusBadge | Libellé léger sans pilule ; couleur réservée aux états utiles |
| MessageBanner | Texte compact et trait sémantique, sans grande carte colorée |
| ResourceRow | Rôle, provenance, choix, action et aperçu dans une ligne compacte |
| WorkflowStrip | Progression existante, état courant, coches SVG et étapes atténuées |
| primary / quiet | Hiérarchie des actions ; pas de styles locaux |

`icons.py` charge les SVG Lucide locaux, version 0.468.0, licence incluse dans le
package. Une seule famille ; pas de téléchargement à l’exécution ni de dépendance
Python supplémentaire. Les chevrons et coches des contrôles Qt viennent du même
jeu. Une icône seule exige tooltip et nom accessible ; les actions métier gardent
leur texte. Les symboles textuels existants de disponibilité restent explicites.

## Catalogue et inspecteur composant

Table de cinq colonnes : composant, package, ressources choisies, état du composant,
stock Lab. UUID et hashes ne figurent pas dans les lignes. Le stock est aligné à
droite et trié numériquement ; les en-têtes trient les autres colonnes. Un filtre
d’état complète la recherche existante (nom, package, état, description et profil
M10). Le tri et le rafraîchissement conservent la sélection par identité, sans
changer l’ordre ni les données du catalogue persistant. Un résultat exclu par un
filtre n’est plus une sélection active. Colonnes redimensionnables, défilement
horizontal disponible en fenêtre étroite, splitter pour ajuster l’inspecteur.

L’inspecteur présente : identité et fabricant/MPN/catégorie M10 lorsque disponible,
package, progression et prochaine action ; ressources ; validation locale ;
inventaire avec emplacements ; bibliothèques. Les outils de gestion et diagnostics
restent accessibles secondairement. L’état Part et la qualification sont distincts.
La présence de fichiers ne signifie pas qu’ils sont choisis ni qualifiés.

Le bouton d’ajout du catalogue est secondaire lorsqu’un composant est inspecté ;
la prochaine action utile est dominante dans l’inspecteur. L’état vide offre un
accès direct à l’ajout. Le modèle mécanique reste partagé : footprint et 3D sont
résolus via le package ; son aide explique cette relation.

Les ressources montrent rôle et provenance sans multiplication de pilules.
« Inspecter » (œil) ne change aucun choix. 3D et PDF restent facultatifs.
Une référence choisie ne reçoit pas automatiquement un PASS. La progression
IDENTIFY → RESOLVE → VERIFY → PUBLISH est une aide : l’appartenance à une
bibliothèque ne prouve jamais une publication.

## Autres inspecteurs et formulaires

Les listes secondaires conservent les master/detail existants. Leur résumé expose
les informations utiles ; provenance et détails techniques sont repliables.
Le résolveur nomme le choix actuel par sa référence lisible ; clé interne et SHA
restent dans les détails du candidat. Les confirmations de remplacement sont
conservées. Les parcours de validation, résolution et import/export gardent leurs
dialogues dédiés lorsqu’une décision explicite est nécessaire.

L’édition ordinaire ouvre une fiche non modale, une seule à la fois par fenêtre.
Une seconde demande ramène la fiche ouverte ; elle ne remplace pas son brouillon.
Fermer l’application avec cette fiche ouverte la ramène au premier plan ; fermer
ou enregistrer la fiche avant de quitter. Enregistrer conserve les validations
existantes et rafraîchit les vues ; Annuler n’enregistre rien.

Les formulaires ont un titre métier, une section identité ou quantités/emplacement,
les références nécessaires et une aide repliable. Associations de fichiers ou de
composants dans une disclosure distincte. * marque les champs requis ; quantité
alignée à droite, validation existante inchangée. Les actions restent hors du
contenu défilant. Les UUID restent des données de sélection internes.

## États, feedback et actions

Ambre d’identité : sélection, focus et action primaire. Vert : PASS/succès.
WARNING / STALE gardent leur ambre sémantique `#e8b76c`, rouge ERROR `#f09595` et
INFO son trait bleu et son texte secondaire existants. La sélection garde un texte
neutre, les avertissements un libellé explicite et un texte sémantique ; la couleur
seule ne définit jamais un état. Les bleus des pins et couches SilkS des aperçus
KiCad restent des couleurs techniques inchangées. Voir
[BRANDING.md](BRANDING.md). Provenance et métadonnées
ordinaires restent neutres. Tous les états portent un texte explicite.

Trois niveaux visuels : primaire, secondaire, discret (`quiet`). Le rôle
`destructive` réserve le rouge aux actions dangereuses ; aucun nouveau geste de
suppression n’est ajouté. Une action dominante par contexte local. Les messages
précisent l’échec ou le résultat et s’effacent lors d’un changement de contexte.
Loading reste visible via les workers/progressions et contrôles désactivés existants.
Aucune popup ajoutée pour un succès ordinaire. Focus clavier visible ; Tab et
copier/coller restent disponibles.

## M8, M10, SnapMagic et M11

M8 conserve l’aperçu avant import, les conflits bloquants, le second contrôle et
la restitution/reconstruction explicites. Les versions restent immuables.

M10 conserve saisie/proposition/comparaison et acceptation par champ. La source
proposée reste visible ; la référence technique complète est repliable. Les
PDF sont lus depuis leurs données locales ; téléchargements uniquement depuis
les domaines explicitement autorisés. Aucun domaine préautorisé.

SnapMagic reste dans le résolveur, après les ressources locales. Configuration,
MPN exact, source, droits déclarés, import puis choix explicite restent séparés.
Sans contrat partenaire, aucune recherche réelle ni résultat simulé en production.

L’assistance M11 est accessible directement depuis le composant sélectionné et
reste intégrée à Documentation, sans chatbot ni nouvel espace principal. Le
raccourci ouvre le contexte sans préparer ni envoyer de requête. Configuration,
destination/modèle, relecture des données, consentement par requête et acceptation
humaine restent inchangés. Zones de texte compactes et défilantes, suggestion
explicitement proposée, champs IA décochés par défaut. Aucun score inventé ni
envoi automatique de fichier. Les workers protègent les changements de contexte
et la fermeture pendant une requête.

## Aperçus et responsive

Les aperçus A1 restent disponibles et adaptés au fond sombre : symboles,
footprints et PDF multipages, zoom, provenance et SHA. Ils sont non modaux et
en lecture seule. Couleurs des couches centralisées, dessin distinct de la
qualification ; limites explicites dans [ASSET_PREVIEWS.md](ASSET_PREVIEWS.md).
A2 ajoute un viewer 3D non modal avec les mêmes contrôles/provenance : rotation,
zoom, recentrage et vues standard. STEP utilise FreeCAD local facultatif ; WRL
fonctionne sans logiciel supplémentaire, dans le sous-ensemble documenté.
Chargement en arrière-plan et état d’erreur intégré ; fermeture protégée pendant
la préparation. Aucun générateur ajouté.

Fenêtre initiale 1200×800, minimum 820×600 ; vérifier aussi 900×680 et 1600×950
(selon écran). Sidebar stable, splitters redimensionnables, défilement des détails
et des champs ; aucune géométrie absolue de page. Contrôles de validation/envoi
hors des champs défilants. Vérifier vide, rempli, sélection, loading, warning et
error sur les écrans affectés. Les tests Qt complètent l’inspection native.

Checkpoint accents ambre : 394 tests réussis, Ruff check/format et mypy strict
réussis. Inspection native macOS du catalogue, inventaire, bibliothèques, KiCad,
publications et paramètres ; parcours Documentation, M8, SnapMagic et IA avec
fixtures hors ligne. Tailles normale/étroite/large, normal, sélection, disabled et
focus contrôlés ; hover et pressé vérifiés aussi par rendu QStyle déterministe.
Aucun changement de workflow. Windows/Linux non inspectés nativement.



## Prototype UX FabParts 2.0 (isolé)

Le prototype `prototypes/fabparts-ux/` suit la spécification `docs/UX_SPEC.md`,
sans changer les écrans PySide décrits ci-dessus. Son autorité visuelle est
`.agents/skills/fab-design-system/` : graphite, Inter, contrôles de 28 px,
ambre limité au logo QFP existant et au filet supérieur, bleu pour l’action et
la sélection. Le texte des primaires sombres utilise le token `--bg-control`
pour atteindre 6,35:1 de contraste. Cette adaptation et l’écart avec l’ancienne
convention d’accent suivent les règles de ce guide.

Bibliothèques → ajout guidé → fiche, préparation et synchro séparées, quatre
ressources visibles ensemble et détails techniques repliables. Données, aperçus,
validations et synchronisations sont explicitement de démonstration. À moins de
1000 px, la fiche remplace l’inspecteur latéral. Les captures clair/sombre et les
limites de vérification figurent dans le compte rendu ; aucune refonte du moteur
ni décision de packaging desktop n’est incluse.

### Consolidation Prototype 02

L’acceptation d’une proposition est distincte de la confirmation finale simulée.
L’action groupée indique son périmètre : « Accepter les propositions éligibles » ;
elle exclut les fichiers fournis, les choix individuels, les conflits et les
ressources absentes. Un changement d’identité/boîtier conserve les ressources
précédentes et rend visibles les associations à revoir. Retirer une proposition
ne doit pas en créer une autre implicitement.

« Enregistrer le brouillon » conserve À compléter ; « Valider et enregistrer »
confirme seulement l’état simulé permis par les ressources acceptées. L’assistant
annonce cet état comme « État après confirmation ». Les fichiers utilisateur
exigent un choix individuel ; aucun aperçu illustratif n’atteste leur validité.

Pour une donnée manquante qui appelle une action, préférer « Boîtier à préciser »
et « Choisir un boîtier » à un tiret seul. Aides courtes par ressource : symbole
nécessaire au schéma, empreinte au PCB, 3D facultative, datasheet recommandée.
Les illustrations des fixtures et le nombre de contacts affiché doivent être
cohérents ; annoncer l’absence d’illustration lorsqu’aucune fixture n’existe.
La fiche À compléter offre « Reprendre la préparation » sur le même composant.
Ces conventions concernent le prototype isolé, sans redéfinir les validations
réelles du moteur ni modifier `UX_SPEC.md`.

## Aperçus Tauri TECH-02A

Les quatre cartes UX 02 sont conservées. La sélection métier est l’aperçu initial ;
le menu « Aperçu » consulte une ressource associée sans la sélectionner en base.
Les identités et origines affichées viennent du moteur. « Voir » / « Ouvrir »
agrandissent la consultation avec retour à la fiche ; l’avertissement « ne constitue
pas une validation » reste explicite. Le modèle 3D annonce une étape ultérieure.

Le SVG utilise les jetons existants : cuivre/pads `--accent`, pad 1 `--accent-text`,
sérigraphie `--text-primary`, fabrication `--info`, courtyard `--text-secondary`.
Le perçage reprend `--bg-workspace` ; les numéros ont un contour de contraste.
Ce code couleur décrit des couches, sans attribuer un statut de qualification.
Les coordonnées sont en mm et les limites visibles viennent des primitives,
jamais du nom d’un boîtier. Le zoom est centré et borné, avec recentrage ; le
sélecteur unité/variante et les couches ne changent aucune donnée métier.

## Aperçus Tauri TECH-02B

La carte Modèle 3D utilise le même sélecteur de ressource associée et le même
dialogue que les aperçus TECH-02A. La consultation d'un modèle associé ne change
pas la sélection métier. OrbitControls : glisser gauche pour tourner, molette
pour zoomer, clic droit/Maj-glisser pour déplacer ; le bouton main active aussi
le déplacement au bouton gauche. Cadrage et vues standard restent dans une petite
barre d'outils, traduite FR/EN. Z est vertical ; face vue depuis −Y, arrière depuis
+Y, dessus +Z, dessous −Z, isométrique depuis (+X,−Y,+Z).

Le cadrage utilise les bounds réels, avec recentrage de présentation seulement.
Le fond reprend `--bg-workspace`, les commandes les tokens communs et la sélection
bleue. Lumière neutre ambiante/directionnelle, matériaux simples ; aucun décor ou
modèle de remplacement. Une erreur WebGL/conversion, une ressource manquante ou
un aperçu partiel sont explicites. Un état de chargement représente l'activité
sans pourcentage inventé. Les warnings et unités restent lisibles dans le dialogue.
Les coordonnées WRL ne permettent pas, à elles seules, de déduire une échelle
physique ; STEP est en mm. Aucun aperçu ne vaut validation mécanique.

## Ingestion réelle Tauri TECH-03

Le parcours reprend les trois étapes UX 02 : informations/fichiers,
identification/package, puis quatre ressources et confirmation. Le bouton
d'ajout et la reprise d'un DRAFT sont disponibles dans la session sandbox writable.
Une référence suffit ; le package et les fichiers restent facultatifs. Aucun
package ni choix de ressource n'est déduit silencieusement du nom d'un fichier.

Le sélecteur natif prépare les fichiers ; leur présence ne signifie pas import
canonique. La grille conserve simultanément les quatre aperçus, avec une hauteur
compacte et le PDF cadré sur sa page entière. Recherche et choix restent proches
de chaque carte ; les détails peuvent défiler sans masquer l'action finale.
Provenance, sélection, UNCHECKED et DRAFT sont distincts. Une confirmation backend
effective précède le message « Enregistré », puis la liste et la fiche sont rechargées.

Un doublon propose consultation, ajout à une autre bibliothèque ou variante
explicitement confirmée. Une seule Part peut apparaître dans plusieurs bibliothèques.
Le package partagé conserve ses choix mécaniques ; un conflit exige un package
distinct nommé. La reprise restaure les valeurs et enregistre les appartenances
cochées, avec détection des modifications concurrentes.

Le double clic est bloqué pendant confirmation ; en cas de résultat incertain,
l'interface consulte le reçu et propose la récupération, sans annoncer de succès
prématuré. Les contrôles du parcours sont traduits FR/EN ; les diagnostics moteur
hérités encore en français sont une réserve explicite. Les preuves natives en
clair/sombre et fenêtre étroite figurent dans [TECH-03](FABPARTS_2_TECH_03.md).

## TECH-04A — Paramètres et données

Le mode personnel expose un bouton Paramètres dans la barre existante. Trois
sections partagées présentent le workspace actif, la sauvegarde et la restauration.
Les chemins longs se replient ; l'espace reste défilable. Réutiliser les tokens,
Section et boutons existants, sans nouveau thème.

Tous les nouveaux libellés sont FR/EN. La source est choisie dans un sélecteur
macOS ; le bouton Restaurer n'apparaît qu'après vérification. La confirmation
native indique la conservation des données précédentes. Pendant l'opération les
actions sont désactivées ; aucun succès n'est anticipé. Après restauration, les
écritures restent bloquées et un bouton explicite redémarre le moteur.

## TECH-04B — Validation et préparation

La fiche présente la validation technique séparément de l'état métier. Afficher
À compléter / Prêt pour schéma / Prêt pour PCB uniquement depuis les preuves
actuelles projetées par le backend ; un aperçu ou une association ne vaut jamais
validation. Un rapport STALE ou une erreur de lecture retire toute affirmation
« prêt ». Les anciens constats sont explicitement présentés comme historiques.

Les erreurs bloquantes sont lisibles ; les réussites sont repliées. Les WARNING
s'examinent avant une case de confirmation propre au rapport, jamais précochée.
Une réponse neuve ou un changement de contexte réinitialise la confirmation.
La qualification de bibliothèque reste un rapport simple avec accès aux membres,
sans commande de publication. Voir les limites précises dans
[FABPARTS_2_TECH_04B.md](FABPARTS_2_TECH_04B.md).

### Publications KiCad — TECH-05A

L’action Publications KiCad appartient à la bibliothèque sélectionnée. Le rapport
Collection M5, indépendant des rapports Part, conditionne la préparation. Un résumé
paginé affiche composants, ressources, version et WARNING acceptés ; une case vide
et une confirmation explicite précèdent l’écriture immuable. Les refus du builder
restent visibles. Les versions affichent « Non vérifiée » jusqu’au contrôle effectif,
et ce contrôle ponctuel est oublié à l’actualisation. Les détails historiques ne
prétendent pas qualifier le catalogue courant.

Après réponse incertaine, une demande persistée côté interface bloque tout nouvel
essai jusqu’à consultation du COMMIT dans le même espace de données. La reconnexion
n’envoie jamais une seconde publication. La reconstruction utilise un sélecteur natif
pour le dossier parent et un sous-dossier neuf généré par l’hôte. L’aide parle
uniquement d’intégration de **projet** `${KIPRJMOD}`. Aucune installation globale,
activation de version ou synchronisation n’est proposée. Tokens, densité, thèmes et
composants FabApps existants sont conservés ; textes FR/EN typés.

### Intégration globale KiCad — TECH-05B

La section Intégration KiCad dans Publications ajoute l'activation globale aux
reconstructions de projet TECH-05A. Publier ne change jamais la version active.
Afficher cible, active/dernière et état réel ; l'état sélectionné n'est pas une
preuve de validation. Le résumé de chaque activation/rollback/reprise exige une
case vide avant application. Les chemins et nicknames techniques restent repliés.

Fermer KiCad avant mutation et indiquer son redémarrage, sans promesse de reload.
Une erreur retire l'ancienne preuve de vérification. Après réponse incertaine,
relire le journal sans rejouer l'écriture. La reprise reste disponible si M7 est
illisible. Les décalages après restauration TECH-04A exigent une action explicite.
Réutiliser Disclosure, boutons et tokens existants ; actions qui se replient et
texte long sécable, FR/EN et clair/sombre. Pas de nouveau thème ni écran de réglages.

### Cadrage des aperçus — finitions QUAL-01

Le viewer SVG cadre le groupe visible après chargement des polices, avec une marge
proportionnelle de 8 % et une réserve pour les traits. Ne pas imposer de taille
physique minimale aux petits symboles. Recalculer pour l'unité/variante et les
couches affichées ; conserver proportions, zoom manuel, recentrage et agrandissement.
Les bornes conservatrices du moteur restent le repli, sans changement du parseur.
