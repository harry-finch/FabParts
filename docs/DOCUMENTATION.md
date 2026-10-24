# Identification et datasheets — M10

Dans **Composants → Documentation**, choisir le composant, ou ouvrir
**Identification et datasheets…** depuis sa fiche.

## Identification relue

Constructeur, référence constructeur (MPN), catégorie et notes d’identification
sont des champs supplémentaires. Le nom et la description du composant restent
ceux du catalogue. Constructeur, MPN et catégorie sont visibles sur sa fiche ;
les quatre champs sont recherchables dans le catalogue.

Saisir les champs et une source, puis **Comparer la saisie**. Une proposition
JSON locale peut aussi être lue sans enregistrer de données. L’aperçu montre les
valeurs actuelles et proposées : les champs en conflit sont décochés. Accepter
uniquement les champs souhaités ; remplacer une valeur renseignée exige de la
cocher et de confirmer explicitement son remplacement. Ignorer quitte l’aperçu
sans appliquer la proposition. Une autre modification depuis l’aperçu bloque
l’acceptation et impose une nouvelle comparaison.

L’historique conserve source déclarée, origine, référence, date et valeurs avant /
après de chaque acceptation. Une source déclarée constructeur ou tierce ne
constitue pas une vérification de son authenticité. Le profil et son historique
restent dans la base SQLite locale.

Exemple de proposition locale UTF-8, maximum 64 Kio :

```json
{
  "format": "kipart-identification/1",
  "source": {
    "label": "Documentation constructeur",
    "reference": "document:référence-et-révision",
    "origin": "MANUFACTURER"
  },
  "fields": {
    "manufacturer": "Constructeur",
    "mpn": "Référence",
    "category": "Résistances",
    "notes": "Informations relues"
  }
}
```

Origines acceptées : `USER_PROVIDED`, `MANUFACTURER`,
`TRUSTED_THIRD_PARTY`. Champs absents laissés inchangés, valeur vide permettant
un effacement confirmé. Chaque valeur est limitée à 4 096 caractères ; nom et
référence de source à 2 048. Aucun scraping ni extraction automatique de PDF.

## Documents conservés

**Datasheets & documents** présente les documents et leurs détails.
**Ajouter ou décrire un PDF…** ouvre le formulaire défilant, avec actions fixes.
Renseigner titre et source ; révision, date `AAAA-MM-JJ` et langue sont facultatives.
Les types datasheet, note d’application et errata sont descriptifs ; ils utilisent
le rôle d’asset PDF `DATASHEET` existant.

- **Décrire le PDF géré** associe un PDF existant et enregistre sa fiche descriptive.
- **Importer un nouveau PDF…** ajoute un asset et une fiche descriptive.
- **Restituer une copie du PDF…** vérifie le hash et refuse un fichier de sortie existant.

Chaque couple composant / asset possède une fiche descriptive immuable. Une
nouvelle version de fichier est un nouvel asset ; les précédentes restent
conservées. Des octets identiques peuvent partager le blob adressé par hash.
L’asset, l’association et sa fiche sont enregistrés en une transaction SQLite.
Un échec ne laisse aucune association partielle ; un blob copié avant un échec
SQLite peut rester orphelin, conformément au store M2.

L’ajout n’effectue aucun choix de ressource et ne qualifie aucun PDF. Utiliser
**Ressources locales** pour le choix M4, puis la validation M5. Les PDF déjà
présents avant M10 restent dans le catalogue et le sélecteur même sans fiche.
L’import local reprend les contrôles M2 de format, hash et disponibilité ;
l’analyse complète du contenu documentaire n’est pas réalisée.

## Téléchargement constructeur optionnel

Aucun domaine n’est préautorisé et le téléchargement est désactivé par défaut.
Dans le formulaire d’ajout, ouvrir **Téléchargement constructeur — configurer**,
activer l’accès, saisir les domaines DNS exacts en minuscules séparés par des
virgules, puis **Enregistrer l’autorisation**. Cette action ne lance aucune requête.
Le réglage reste local dans `config/datasheets.toml`, sous le dossier de données.

Saisir l’URL HTTPS finale du PDF et cliquer **Télécharger un nouveau PDF**.
L’hôte doit être explicitement autorisé ; ni joker, sous-domaine implicite,
adresse IP, identifiants URL ou port différent de 443. Une redirection est
refusée : saisir et autoriser sa destination finale explicitement. L’URL devient
la source constructeur du nouvel asset et de sa fiche descriptive. L’autorisation
est revérifiée avant l’enregistrement, y compris après un changement de réglage.

L’adaptateur utilise HTTPS standard, une attente réseau de 8 secondes, un budget
de lecture de 20 secondes contrôlé entre blocs et une limite de 32 Mio. Une
signature `%PDF-` est requise dans les premiers 1 024 octets ; elle ne garantit
pas la validité complète du PDF. Aucun compte, jeton, retry ou cache distant.

L’attente a lieu dans un worker ; la fermeture attend sa fin, sans annulation
immédiate. Une panne HTTP, réseau ou TLS, un PDF incorrect, un fournisseur absent
ou un réglage invalide produit un message explicite et préserve les documents.
Saisie locale, import, consultation et restitution restent possibles sans réseau.
Les réglages M9 et M10 sont indépendants.

## Portabilité et limites

La migration `0006_documentation` ajoute deux tables sans réécrire le catalogue.
Le retour au schéma précédent est refusé si ces tables contiennent des données.

Les publications historiques restent immuables. Le PDF choisi conserve octets,
hash et provenance d’asset dans les publications M7 et archives `.kiparts` M8 ;
les références locales y sont normalisées selon les règles M8 existantes.
Les profils d’identification, leurs historiques et les fiches descriptives M10
restent locaux et **ne sont pas transférés par `.kiparts` v1**. Sauvegarder le
dossier de données complet pour conserver ces informations.

Pas de recherche automatique de datasheet, extraction de métadonnées PDF, service
tiers distant, IA ni génération. Les téléchargements ont été vérifiés avec
réponses déterministes ; aucun domaine constructeur réel n’a été autorisé dans
les données utilisateur pendant ce checkpoint.
