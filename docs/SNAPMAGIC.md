# SnapMagic / SnapEDA — M10.5

## État de l’intégration

Le resolver optionnel, l’interface, l’import géré et la provenance sont implémentés.
**La connexion HTTP réelle n’est pas implémentée : elle attend le contrat API
partenaire autorisé.** Les scénarios de recherche et téléchargement sont vérifiés
avec un partenaire simulé, exclusivement dans les tests. L’application ne fournit
aucun résultat fictif en production.

La [demande d’accès officielle](https://www.snapeda.com/get-api/) et
[l’aide officielle](https://support.snapmagic.com/en/articles/2957835-does-snapmagic-have-an-api)
confirment un accès API à demander. Les pages publiques consultées le 11 octobre
2026 ne décrivent pas l’authentification, les endpoints de recherche/téléchargement,
les schémas de réponse ni les quotas du contrat applicable à cette application.
Une connexion au site par LinkedIn ne fournit pas ces éléments. Aucun cookie de
session, identifiant de connexion au site ou compte utilisateur n’est utilisé.

## Parcours utilisateur

Depuis une fiche composant ou package, ouvrir **Résoudre les ressources**.
Les sources locales et officielles restent dans leur onglet habituel ; l’onglet
**SnapMagic optionnel** présente son activation et son état sans erreur au démarrage.

1. Choisir le rôle : symbole, footprint ou modèle 3D.
2. Renseigner le MPN exact et éventuellement le constructeur. L’identification
   M10 préremplit ces champs pour un composant ; modifier le contexte efface les
   anciens candidats. Le nom du composant n’est pas présenté comme un MPN fiable.
3. Activer et enregistrer le fournisseur. Sans secret il reste « non configuré » ;
   avec un secret mais sans client partenaire, il indique « contrat API requis ».
4. Lorsque le client partenaire autorisé sera disponible, **Rechercher** produira
   des candidats distants sans importer de fichier. La recherche locale est
   rafraîchie d’abord. Le MPN et le constructeur renseigné doivent correspondre
   exactement, sans tenir compte de la casse ; aucune correspondance approximative.
5. Inspecter le candidat : origine tierce, identifiant, source publique, format,
   package, date et informations de licence disponibles. Il s’agit d’une inspection
   de métadonnées, pas d’un rendu géométrique.
6. **Importer le candidat inspecté** télécharge seulement ce candidat, contrôle
   son contenu, calcule SHA-256 et crée un nouvel asset `MANAGED_FILE` dans l’Asset
   Store. La validation reste `UNCHECKED`. Le choix existant ne change pas.
7. Revenir aux sources locales, choisir explicitement l’asset et confirmer tout
   remplacement. Appliquer la qualification M5 habituelle avant publication ;
   les WARNING 3D demandent toujours acceptation explicite. Une transformation
   3D cohérente dans le footprint reste nécessaire à la construction M6/M7.

Recherche/téléchargement utilisent un worker sans accès SQLite. La fermeture et
le changement de rôle sont protégés pendant l’opération ; l’import local s’effectue
ensuite sur le thread UI. Aucun téléchargement de masse ni cache persistant ajouté.

## Configuration et frontière partenaire

Dans le répertoire de données actif, `config/snapmagic.toml` contient uniquement :

```toml
enabled = false
```

L’activation se règle dans le panneau. `KIPART_SNAPMAGIC_CREDENTIAL` est le point
d’entrée réservé à un secret partenaire opaque, lu en mémoire par
`EnvironmentCredential`. **Renseigner cette variable ne suffit pas à connecter
l’application actuellement.** Aucune méthode d’authentification HTTP n’est présumée.
Le secret n’est pas écrit dans le TOML, SQLite, les manifests ou les logs.

`SnapMagicAdapter` accepte un `PartnerClient` injectable ; ses `SnapMagicRecord`
sont un contrat **interne normalisé**, pas le schéma JSON de SnapMagic. La composition
normale instancie l’adaptateur sans ce client. Pour connecter le service, il faudra
obtenir et vérifier endpoints, authentification, formats, quotas et droits, puis
implémenter ce client HTTP. Les destinations autorisées, redirections, limites de
lecture avant matérialisation des octets et envoi du secret devront être contrôlés
par ce client. Aucun endpoint deviné, scraping ou authentification par navigateur.

Le port `ThirdPartyProvider` et `ThirdPartyResolver` restent indépendants du fournisseur.
Priorité : utilisateur → géré → KiCad local officiel → KiCad distant officiel →
constructeur → tiers. Les assets importés conservent `TRUSTED_THIRD_PARTY` et leur
rang de source ; ils ne deviennent pas des candidats officiels ou constructeurs.

## Fichiers et import

Le contrôle local accepte `.kicad_sym`, `.kicad_mod`, `.step`/`.stp`, `.wrl`.
Ces formats sont **testés avec fixtures** ; leur disponibilité dans le contrat API
partenaire n’est pas vérifiée. Les anciens `.lib`/`.mod` ne sont pas convertis.
Le [guide d’import du fournisseur](https://api.snapeda.com/about/import/) ne suffit
pas à garantir la disponibilité de symboles modernes `.kicad_sym` via l’API.

Les octets téléchargés sont bornés à 32 Mio. Pour un ZIP, seul le membre correspondant
au nom du fichier choisi est lu en mémoire ; aucune extraction de chemins. Limites :
64 entrées, 64 Mio décompressés au total, 32 Mio par fichier ; chemins traversants,
liens symboliques, chiffrement et ambiguïtés refusés. HTML, PDF et formats incohérents
sont rejetés. L’inspection réutilise les parseurs/sondes existants dans un répertoire
temporaire automatiquement nettoyé. Elle contrôle la structure, pas la conformité
électrique ou dimensionnelle. Le SHA-256 annoncé, s’il existe, doit correspondre.

Les octets retenus passent par l’Asset Store M2. Aucun lien vers le fichier temporaire
ne devient une dépendance. L’import crée un UUID distinct ; un blob peut être
réutilisé par déduplication, jamais une provenance utilisateur écrasée.

## Provenance et redistribution

La migration additive `0007_asset_provenance` ajoute `assets.provenance_json` nullable.
Les assets antérieurs sont inchangés. La provenance d’un import est immuable :
fournisseur, identifiant, source publique, dates de résolution/import, SHA-256, MPN,
constructeur, package, licence/URL/attribution et état `allowed`, `restricted` ou
`unknown`. Un état établi exige une référence de droits explicite. Une URL signée
ou contenant des paramètres n’est pas une source persistable ; le client devra
séparer la source publique de l’URL de téléchargement. Les métadonnées reçues ne
peuvent pas contenir le secret partenaire connu.

L’[aide sur les licences](https://support.snapmagic.com/en/articles/2957814-what-is-the-license-for-symbols-and-footprints)
présente une licence CC BY-SA avec exception de conception pour les symboles et
footprints. Les [conditions du service](https://www.snapeda.com/about/terms/)
comprennent aussi des restrictions d’accès, d’usage logiciel et de redistribution.
**Ces pages ne prouvent pas un droit général de redistribuer chaque fichier via
KiPart Manager.** Aucune licence globale n’est déduite, aucune autorisation inventée ;
`unknown` est la valeur par défaut, même si un nom de licence est communiqué.
Le futur contrat partenaire doit préciser les droits pertinents, notamment des
modèles 3D. Ces informations sont des faits déclarés, pas un avis juridique.

M8 v1 et les manifests M7 restent inchangés. Ils conservent origine, source et hash,
mais **ne transportent pas cette provenance détaillée ni ses droits**. Un transfert
sur une nouvelle base perd donc ces champs ; un réimport dans la base d’origine
préserve sa provenance détaillée. Aucun contrôle automatique de redistribution n’a
été ajouté à l’exporter M8. Le Publisher/exporter devra exploiter ces informations
lors d’une évolution dédiée ; un export actuel ne vaut pas autorisation.

## Hors ligne et limites

Aucune requête au démarrage, à la résolution locale ou à l’ouverture de la fenêtre.
Fournisseur désactivé/absent, secret absent, contrat absent et panne restent facultatifs.
Les erreurs du client sont normalisées sans contenu confidentiel ; un rate limit
peut indiquer un délai explicite reçu, sans inventer de quota ou lancer de retry.
Les fichiers importés restent restituables, qualifiables et publiables hors ligne.

Pas d’IA M11, génération, synchronisation, nouveau moteur de preview, cache,
nouvelle dépendance ou refonte M8. Voir [la décision](adr/0001-third-party-assets.md).
