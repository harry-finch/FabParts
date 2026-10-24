# ADR 0001 — Frontière partenaire optionnelle et provenance d’asset durable

Date : 11 octobre 2026. Statut : accepté dans M10.5 ; connexion HTTP différée.

## Contexte

SnapMagic publie une demande d’accès API, mais aucun contrat technique applicable
n’a été fourni. La connexion LinkedIn au site n’est pas une authentification API.
M10.5 autorise explicitement une intégration avec faux fournisseur lorsque l’accès
partenaire manque. La provenance riche et les droits doivent survivre au téléchargement.

## Décision

Créer un port tiers normalisé indépendant de SnapMagic, avec recherche explicite et
import séparé. L’adaptateur prépare la normalisation autour d’un `PartnerClient`
injectable ; aucun client HTTP par défaut, endpoint supposé ou fallback fictif en
production. Le secret éventuel vient de l’environnement et reste en mémoire.

Conserver une provenance immuable, générique, dans une colonne JSON nullable d’Asset.
Les dates, hash et références restent attachés à l’asset géré ; la licence et les
états de redistribution sont des déclarations distinctes. `unknown` est le défaut.
Un import ne choisit ni ne qualifie automatiquement l’asset. Les tiers restent après
les ressources utilisateur, gérées, officielles et constructeurs.

## Conséquences

Tout le parcours local et les scénarios de panne sont testables sans compte ni réseau.
La recherche réelle reste indisponible jusqu’à la vérification et implémentation du
client partenaire. L’adaptateur préparé n’est pas un client HTTP fonctionnel.

Migration additive, downgrade refusé si la provenance serait perdue. Les migrations
SQLite ouvrent explicitement une transaction pour annuler aussi le DDL si une étape
ultérieure refuse le downgrade ; schéma et version restent cohérents.

M8 v1 n’est pas refondu : ses copies conservent source/origine/hash, mais pas les
nouveaux champs de licence. Un réimport compatible garde la provenance locale
existante. Une évolution dédiée devra porter ces droits dans les archives et décider
comment les appliquer à l’export, sans interpréter l’absence de champ comme permission.
