# M9 — Recherche officielle KiCad distante optionnelle

## Utilisation

Le cœur reste local. Aucun accès distant au démarrage, à la recherche locale,
à la qualification, à la publication ou au transfert `.kiparts`.

1. Commencer par les ressources locales du composant/package : utilisateur,
   catalogue géré, index officiel installé. Le resolver propose ensuite
   « Compléter avec la recherche officielle distante… » pour les rôles KiCad.
2. Dans **KiCad local → Officiel distant · optionnel**, ouvrir **Accès distant**,
   autoriser GitLab et enregistrer une révision. Les Paramètres donnent aussi
   accès à cet onglet. L’accès est **désactivé par défaut**.
3. Saisir le type et une bibliothèque précise, sans suffixe : `Device` pour les
   symboles, `Resistor_SMD` pour les footprints/modèles. Filtrer puis cliquer
   **Rechercher en ligne**. Aucun appel réseau à la frappe.
4. Comparer les candidats distants, leur origine, révision, commit et source.
   **Télécharger comme nouvel asset** conserve le fichier dans l’Asset Store,
   avec un nouvel UUID, SHA-256 et origine `KICAD_OFFICIAL`, état `UNCHECKED`.
5. Retourner aux ressources locales du composant/package et choisir l’asset.
   Un choix existant exige toujours la confirmation explicite de remplacement.
   Importer n’associe pas, ne choisit pas et ne qualifie pas automatiquement.

Les candidats utilisateur, gérés et officiels installés gardent leur priorité.
Les assets importés depuis cette source distante viennent après ces trois groupes.
Deux imports explicites créent deux fiches distinctes ; leurs octets identiques
se dédupliquent dans le store. Les sources utilisateur et bibliothèques installées
ne sont jamais modifiées.

## Source et versions

L’adaptateur lit uniquement les trois dépôts officiels du groupe GitLab KiCad :

- `kicad/libraries/kicad-symbols` ;
- `kicad/libraries/kicad-footprints` ;
- `kicad/libraries/kicad-packages3d`.

L’hébergement officiel est documenté par [KiCad](https://www.kicad.org/libraries/download/).
L’adaptateur utilise les API publiques GitLab
[commits](https://docs.gitlab.com/api/commits/),
[tree](https://docs.gitlab.com/api/repositories/) et
[files/raw](https://docs.gitlab.com/api/repository_files/), sans compte ni token.
Une branche/tag simple ou un SHA Git de 40 caractères est accepté. La valeur
initiale est `9.0.0`, vérifiée sur les trois dépôts ; ce n’est pas une promesse
que chaque révision existe dans chaque dépôt.

Chaque recherche résout la révision en commit. Arborescence et téléchargement
utilisent ensuite ce commit, même si la branche bouge. La provenance de l’Asset
conserve le lien GitLab avec commit, chemin et révision demandée. Les symboles
conservent le SHA-256 du fichier cherché ; footprints/modèles comparent les octets
au blob Git annoncé, puis le store calcule leur SHA-256.

Le fichier multi-symboles complet est conservé, avec `AssetFile.symbol_name`
pour l’entrée choisie. Cela préserve les parents `extends` sans générer un
nouveau symbole. Probe, validation, builder et transport M8 emploient déjà ce
sélecteur. Les anciennes publications restent immuables.

## Configuration et séparation

`<data-dir>/config/remote-kicad.toml` conserve seulement :

```toml
enabled = false
revision = "9.0.0"
```

Configuration propre au poste, non transférée dans `.kiparts`. Enregistrer est
une opération locale atomique. Un fichier invalide affiche une erreur sur la
fonction distante ; il peut être corrigé depuis la même UI. Il ne bloque pas
le catalogue et n’active jamais le réseau implicitement.

`RemoteLibraries` orchestre les ports `RemoteProvider` et `RemoteSettings`.
`OfficialGitLab` adapte HTTP et les parseurs existants ; `TomlRemoteSettings`
adapte la configuration. Le domaine ne dépend d’aucun client HTTP. Bootstrap
peut omettre le service ou composer un fournisseur absent. `LocalResolver`
n’appelle aucun adaptateur distant, y compris si celui-ci est activé/en panne.

Les requêtes travaillent dans un thread Qt avec progression indéterminée.
Les contrôles de la tâche sont désactivés pendant son exécution ; la fermeture
attend sa fin. La sauvegarde de l’Asset se fait sur le thread principal après
contrôle du téléchargement et de la configuration actuelle. Il n’y a aucune
modification du schéma, du manifest M7 ou du format `.kiparts`.

## Erreurs et limites

- Recherche dans **une bibliothèque précise**, pas un moteur global ni un index
  distant permanent. Symboles : nom/description/mots-clés ; autres : nom de fichier.
- 200 candidats affichés au maximum ; 2 000 entrées de dossier au maximum,
  avec signalement des résultats potentiellement incomplets.
- JSON limité à 1 Mio et fichiers à 32 Mio. Timeout HTTP de 8 s ; lecture bornée
  par un budget de 20 s vérifié entre blocs ; pagination par un budget de 45 s
  vérifié entre requêtes. Une requête en cours peut dépasser ce dernier budget.
  Aucun retry automatique, aucune requête périodique, aucun cache cachant une panne.
- Erreurs HTTP, réseau/TLS, réponses invalides, hashes incohérents et formats
  KiCad non supportés sont signalés. Aucun nouvel Asset n’est sauvegardé si
  téléchargement ou vérification échoue. Une erreur de sauvegarde peut laisser
  un blob orphelin, comme pour les imports M2, sans association fictive.
- Symboles regroupés en `.kicad_sym` et footprints modernes selon les bornes du
  parseur M3 ; modèles STEP/STP/WRL. Les dépôts à symboles répartis dans des
  dossiers, formats futurs et pointeurs Git LFS ne sont pas supportés.
- La compatibilité réelle a été vérifiée sur `9.0.0`. Les autres tags/branches
  doivent présenter ces structures/formats ; une révision incompatible échoue
  explicitement. Aucun fallback vers une autre version.
- Le contrôle Git/SHA établit l’identité des octets, pas leur qualification CAO.
  M5 reste obligatoire avant publication ; les limites mécaniques/PDF de M5
  demeurent. Les modèles liés aux footprints doivent être recherchés et choisis
  séparément ; aucune récupération récursive automatique.
- L’import conserve le fichier officiel, sans modifier ses mentions de licence.
  Les conditions de redistribution officielles restent applicables ; M9 n’ajoute
  aucun téléchargement de fournisseur tiers.
