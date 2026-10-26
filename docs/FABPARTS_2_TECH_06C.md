# TECH-06C — Assistance IA facultative

26 octobre 2026 · `tech/06c-ai-assistance`

## Base et périmètre

PR #10 contrôlée sur `fe0359e` : ouverte, sans conflit, sans statut/workflow CI
publié. Fusion par **merge commit** `e321e87c4fafe96ff250b46e28482f96ef60010a`,
présence de TECH-06B vérifiée dans origin/main, synchronisation fast-forward puis
branche exacte TECH-06C créée, sans changement local écrasé.

Audit AGENTS, ASSISTANCE, DOCUMENTATION, TECH-06B, architecture/M11 et ADR 0002/0003/0004.
Skills Fab design system, professional workshop UI, invariant hors ligne,
vérification Python et checkpoint appliquées. Pas de modification PySide.

## Services et parcours

Réutilisation de `Assistance`, `ChatAssistance`, `AssistanceToml`,
`AssistanceRequest`, `MetadataProposal`, `Documentation.accept()` et du dépôt
transactionnel/historique M10. Aucun nouveau moteur, SDK, schéma ou framework.

Paramètres : fournisseur Ollama/Gemini/Chat Completions compatible, endpoint,
modèle existant, activation et état de configuration. Désactivé par défaut.
La disponibilité affichée signifie configuration et clé présentes, pas un test
réseau ni une garantie de modèle accessible. Aucun téléchargement/découverte.

La fiche complète propose une section discrète repliable. Contexte textuel limité
à 16 000 caractères ; identification actuelle facultative et décochée par défaut.
Le JSON utilisateur exact, fournisseur, destination effective et modèle sont
relus avant le consentement de cette requête. Nom/description Part, UUID, chemins,
historique, fichiers, PDF, catalogue et stocks ne sont pas ajoutés au JSON.
L'instruction fixe M11 exige seulement quatre champs JSON et aucun outil.

La comparaison présente actuel/proposé : fabricant, MPN, catégorie, notes.
Toutes les propositions commencent décochées. Un remplacement sélectionné exige
sa confirmation distincte. Accepter transmet seulement champs/capacité/confirmation,
pas une proposition modifiable. Seuls les champs cochés passent dans M10.
Ignorer, modifier ou quitter révoque la session sans écriture.

## Contrats, concurrence et secrets

Commandes privées strictes Python/Rust, permission dédiée :
`assistance_configuration`, `assistance_configure`, `assistance_identification`,
`assistance_prepare`, `assistance_start`, `assistance_status`,
`assistance_accept`, `assistance_cancel`. Refus readonly, restauration en attente
et préparation d'ingestion active ; aucune invocation automatique pendant l'ingestion.

Une session éphémère opaque, bornée à 20 minutes, fixe requête/configuration/Part
et identification attendus. Toute modification les invalide. Un unique worker
reprend le principe borné de TECH-06B, sans SQLite ni Asset Store. Annulation
logique et contrôle de session écartent les résultats tardifs. Une nouvelle
inférence ne peut s'ajouter à un appel encore actif. Navigation locale disponible.
Les budgets HTTP M11 restent 8/30 s par attente, 30 s entre blocs et 256 Kio de
réponse, sans retry automatique. Annuler ne tue pas une attente HTTP engagée.

Le timeout IPC global reste 8 s. Seule `assistance_prepare` accepte une trame
jusqu'à 256 Kio pour les 16 000 caractères Unicode, y compris JSON échappé en
paires de surrogates ; les autres commandes restent à 16 Kio. Réponse IPC globale
inchangée. Les paramètres restent strictement bornés indépendamment de la trame.

Rust conserve `env_clear()` : uniquement GEMINI_API_KEY / KIPART_AI_API_KEY
pour M11, en plus des variables techniques préexistantes. Valeurs vides, de
contrôle ou excessives refusées. Aucun champ de clé ni nouveau stockage ; TOML
existant. Protection des deux clés connues dans contexte/configuration/proposition,
y compris Unicode. Exceptions de fournisseur non reflétées dans l'IPC ; aucun
corps de réponse, prompt ou clé dans les diagnostics.

Acceptation séparée, atomique et optimiste M10. Historique : avant/après des seuls
champs retenus, date, GENERATED_AI, fournisseur/modèle/destination et SHA-256 du
contexte. Pas de prompt complet ni de réponse brute persistés. Pas de retry
automatique d'une acceptation incertaine : relire fiche/historique avant décision.

Les métadonnées du profil M10 ne sont pas des entrées M5 du moteur actuel et ne
modifient ni Part ni ResourceChoice. Aucun changement de qualification automatique,
fingerprint historique, Asset Store, publication M7, writer ou intégration KiCad.
Les mutations pertinentes Part/choix/fichiers continuent à rendre les rapports
STALE selon M5. L'assistance ne constitue jamais une qualification constructeur/CAO.

## Vérification automatisée

- Python complet avec FreeCAD : **652 passed** ; 15 cas d'orchestration nouveaux,
  plus les contrats M11 historiques et toutes les régressions TECH-03 à TECH-06B.
- Ruff/format et mypy : conformes, 268 fichiers formatés / 193 modules typés.
- Rust : **37 passed**, rustfmt conforme.
- Frontend TECH : **99 passed** ; frontend UX : **12 passed**.
- Svelte check : aucune erreur ni avertissement ; builds UX et Tauri ARM64 conformes.
  Avertissement Vite habituel sur la taille des chunks, sans dépendance ajoutée.

Couverture : désactivation, absence de consentement/réseau à la préparation,
clé absente/configuration invalide, trois contrats HTTP simulés, JSON exact et
inclusion contrôlée, limites Unicode et refus des surrogates isolés dans les
propositions, JSON invalide/incomplet/champs inconnus,
contradictions, acceptation partielle/remplacement, ignorance, provenance,
révision/configuration/Part/contexte modifiés, timeout/annulation, écho de secret,
readonly/restauration/ingestion et permissions IPC. Les tests frontend exercent
révocation immédiate, réponse tardive, état décoché, confirmation réinitialisée,
erreur sans retry et absence de faux succès.

## Qualification native et fournisseurs

Bundle macOS ARM64 inspecté nativement sur un espace jetable copié de TECH-06B,
avec les cinq racines workspace/KiCad/documents/cache explicitement isolées et
vérifiées dans l'environnement effectif avant observation. Trois lancements
contrôlés, trois fermetures coopératives ; français/sombre, anglais/clair et
fenêtres d'environ 901, 1440 et 1512 pixels logiques de largeur.

Le faux endpoint a reçu exactement deux appels explicitement autorisés. Aucun
appel au démarrage, à la configuration ou à la prévisualisation. La modification
du texte après consentement a retiré l'autorisation et le JSON préparé. Quatre
propositions décochées ; sélectionner le MPN existant a exigé une confirmation
distincte, avec acceptation bloquée tant qu'elle manquait. La comparaison a été
corrigée pour afficher les valeurs intégrales, y compris en fenêtre étroite.

Une seule catégorie synthétique acceptée : MPN conservé, aucun autre champ,
Part, choix de ressource, rapport, asset, publication ou état métier modifié.
Comparaison SQLite avec TECH-06B : seule la table des profils d'identification
change. Historique GENERATED_AI avec destination/modèle/date et SHA-256 du JSON
exact vérifiés ; aucun contexte complet ou secret. Après redémarrage, profil et
historique conservés. Seconde analyse ignorée : profil et historique inchangés.

Deux clés factices connues atteignent le worker ; une variable secrète factice
supplémentaire n'est pas transmise. Aucun de ces marqueurs dans les diagnostics.
Les treize racines protégées (données/préférences antérieures incluses) restent
identiques. Sauvegarde complète créée et vérifiée. Sur une copie readonly,
les huit commandes IA sont refusées et les empreintes des fichiers sont inchangées.

Captures : [consentement FR sombre](tech06c/consent-exact-payload-fr-dark.jpg),
[comparaison EN claire étroite](tech06c/comparison-replacement-en-light-narrow.jpg),
[historique FR sombre large](tech06c/history-fr-dark-wide.jpg).

Les contrats Gemini, Chat Completions et Ollama sont **simulés** dans les tests.
Ollama est installé mais `ollama list` ne présente aucun modèle : aucune installation,
aucun pull et aucune inférence réelle. Aucun modèle distant n'est configuré dans
les données de test ; aucune clé personnelle utilisée, aucun appel Gemini/OpenAI
live ni dépense. Le faux endpoint Ollama de qualification est exclusivement un
serveur de fixture loopback jetable, hors application et hors dépôt public.
Ces essais ne qualifient pas la précision d'un modèle ou les droits/quota d'un compte.

## Limites et décision

Annulation non préemptive d'une attente système, sans retry automatique. Les
suggestions restent non vérifiées. Fenêtre d'historique limitée aux dix derniers
événements affichés ; l'historique complet demeure conservé en SQLite. Les messages
techniques historiques M11 peuvent rester français en UI anglaise. Qualification
native limitée à macOS ARM64. Le nom de modèle et les politiques de données/quota
du fournisseur doivent être vérifiés par l'utilisateur avant un usage réel.

**GO WITH CONDITIONS** — Fonctionnelle dans le périmètre simulé et natif testé ;
consentement, persistance et isolation validés. Aucune inférence réelle fournisseur
qualifiée : un essai avec un modèle disponible et un compte explicitement autorisé
reste nécessaire avant de revendiquer cette qualification.

Ne pas fusionner TECH-06C. **STOP** ; aucun chantier
suivant, nommage versionné, agent autonome, recherche Web, OCR ou génération CAO.
