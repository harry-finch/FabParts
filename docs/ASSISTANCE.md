# Assistance IA facultative — M11

L’assistance propose uniquement des champs d’identification : constructeur, MPN,
catégorie et notes. L’utilisateur relit et accepte chaque champ dans le parcours M10.
Aucun symbole, footprint, modèle 3D, choix de ressource ou qualification n’est généré
ou modifié par l’IA. Les propositions restent en mémoire jusqu’à acceptation ; ignorer
une proposition ne change ni les valeurs ni leur historique.

## Utilisation

Dans **Composants → Documentation**, choisir le composant puis **Assistance IA ·
optionnelle**. L’identification manuelle et les documents locaux restent disponibles.

1. Ouvrir **Configurer le fournisseur IA**. Choisir Gemini, API compatible OpenAI
   ou Ollama ; renseigner le modèle et enregistrer l’activation. Aucun appel de
   découverte ni téléchargement de modèle n’est déclenché.
2. Saisir/coller le contexte utile : extrait textuel de datasheet, marquage ou
   description, jusqu’à 16 000 caractères. Aucun PDF n’est extrait ou envoyé par
   l’application. Les éventuels chemins/secret saisis volontairement dans le texte
   font partie de ce texte ; relire le contenu avant de l’autoriser.
3. Facultativement cocher l’inclusion des champs d’identification enregistrés.
   Par défaut ils ne sont pas envoyés. Nom/description du Part, UUID, révision,
   historique, fichiers, stocks et catalogue ne sont jamais ajoutés implicitement.
4. **Relire les données à envoyer** montre destination finale, modèle demandé et
   JSON utilisateur exact. Une instruction fixe demande des suggestions JSON, sans
   outils, navigation, commandes ou génération de fichiers.
5. Cocher l’autorisation pour cette requête puis **Demander des suggestions à relire**.
   Modifier contexte, composant ou paramètres invalide cet aperçu et son consentement.
6. La réponse ouvre **Identification**, avec valeur actuelle/proposition et source
   IA explicite. **Tous les champs IA commencent décochés**, même les champs vides.
   Cocher uniquement les changements souhaités ; confirmer explicitement tout
   remplacement d’une valeur existante puis accepter. Ou ignorer sans modification.
7. L’historique M10 conserve les champs acceptés, avant/après, date, origine
   `GENERATED_AI`, destination, modèle demandé, date de réception et hash du contexte
   envoyé. L’instruction et le contexte complet ne sont pas stockés ; le hash
   permet de rattacher un contexte conservé par ailleurs, pas de le reconstituer.

L’IA peut se tromper : le contrôle JSON vérifie la forme, pas l’exactitude des faits.
Une suggestion acceptée n’est pas une certification constructeur ou une validation M5.

## Gemini — fournisseur distant principal

Cliquer **Préremplir l’URL Gemini** :

```toml
# Dans le dossier de données actif : config/assistance.toml
# Le nom de modèle doit être remplacé par celui disponible sur votre compte.
enabled = true
backend = "gemini"
endpoint = "https://generativelanguage.googleapis.com/v1beta"
model = "VOTRE_MODELE_GEMINI"
```

La clé vient de **`GEMINI_API_KEY` dans l’environnement du processus qui lance
KiPart Manager**. Aucun champ de clé dans l’interface ni secret dans ce TOML.
Une application déjà lancée n’hérite pas des changements d’environnement d’un
terminal ouvert ensuite : relancer depuis l’environnement configuré.
Une clé API Gemini est distincte de la connexion à l’interface web Gemini.

Le client appelle l’API native Google : POST
`/v1beta/models/<modèle>:generateContent`, header `x-goog-api-key`,
`systemInstruction`, `contents` et `generationConfig` avec
`responseMimeType = application/json` et `maxOutputTokens = 1600`.
L’origine Gemini est restreinte à l’URL officielle ci-dessus ; aucune URL clé/query.
La réponse doit terminer avec `finishReason = STOP` ; réponses bloquées, incomplètes
ou JSON invalide sont refusées. Aucune option de recherche Web ni fichier joint.

Contrat consulté le 12 octobre 2026 :
[référence GenerateContent](https://ai.google.dev/api/generate-content) et
[sorties structurées](https://ai.google.dev/gemini-api/docs/structured-output).
Le client natif évite de présumer la prise en charge de tous les paramètres de
[l’interface de compatibilité OpenAI](https://ai.google.dev/gemini-api/docs/openai).
Les droits d’accès au modèle, quotas, facturation et politique de données dépendent
du compte et du service choisi ; aucune disponibilité n’est déduite par l’application.

## Ollama sur le poste

Installer/configurer Ollama et un modèle local séparément, puis cliquer
**Préremplir Ollama local** et saisir le nom exact du modèle déjà installé.

```toml
enabled = true
backend = "ollama"
endpoint = "http://127.0.0.1:11434/api/chat"
model = "VOTRE_MODELE_LOCAL"
```

Seul HTTP sur l’adresse littérale loopback `127.0.0.1`, chemin `/api/chat`, est accepté.
Le port peut être adapté ; pas d’hôte distant, identifiants, query ou redirection.
Les proxies d’environnement sont désactivés pour cet appel. Aucune clé distante
n’est lue ni envoyée en mode Ollama.

POST `/api/chat` utilise `messages`, `format = json`, `stream = false` et une
limite `options.num_predict = 1600`. Réponse terminée `done = true` et
`done_reason = stop` requise. Aucun appel pull/install/model discovery ni serveur
fourni par KiPart Manager. Le service Ollama et son modèle local doivent être
opérationnels ; l’absence du service ne bloque pas l’identification manuelle.
La configuration du serveur Ollama reste sous le contrôle de l’utilisateur :
utiliser un modèle exécuté localement pour un traitement sans service distant.
Voir [le contrat officiel](https://docs.ollama.com/api/chat).

## Autres API compatibles OpenAI

```toml
enabled = true
backend = "chat"
endpoint = "https://VOTRE_SERVICE/v1/chat/completions"
model = "VOTRE_MODELE"
```

URL finale HTTPS sur port 443, sans credentials/query/fragment ; secret
`KIPART_AI_API_KEY` dans l’environnement. Une destination Google compatible utilise
`GEMINI_API_KEY`. Aucun secret n’est transmis par redirection.

POST Chat Completions, messages system/user, JSON mode `response_format`,
`stream = false`, `store = false`, `max_completion_tokens = 1600` ; réponse non
refusée avec `finish_reason = stop`. Le modèle/service doit accepter ces paramètres.
Pas de négociation ni fallback de modèle/API. `store = false` est un paramètre
transmis, pas une garantie globale sur la conservation des données par un tiers.
Voir [la référence OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
et [le JSON mode](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).

## Contrôles, persistance et hors ligne

- Configuration atomique TOML, fournisseur désactivé par défaut ; aucun réseau au
  démarrage, à l’ouverture d’une fiche ou à la préparation du contexte.
- Réponse bornée à 256 Kio ; JSON de suggestions jusqu’à 20 000 caractères,
  quatre champs connus au maximum, chacun de 4 096 caractères. Champs inconnus,
  types incorrects, clés dupliquées, blocs Markdown et réponses incomplètes refusés.
- Timeout socket 30 s pour Gemini/Ollama, 8 s pour autres Chat Completions ; budget
  de lecture vérifié entre les lectures, 30 s. Pas de retry automatique, y compris
  HTTP 429. Les erreurs affichées ne reprennent pas le corps ou les secrets.
- Requête/contexte/réponse ne vont dans aucun log ou manifest. Les métadonnées
  contenant la clé connue sont refusées. La provenance locale acceptée conserve
  l’origine IA, pas une origine officielle/constructeur.
- Un worker ne touche pas SQLite. Pendant l’analyse, changement de composant,
  actions Identification/Documents et fermeture sont protégés. Une révision
  changée pendant l’analyse ou une activation révoquée écarte la proposition.
- Acceptation atomique et contrôle optimiste M10 ; aperçu obsolète refusé.
  Aucun nouveau schéma SQL ni migration : l’historique JSON M10 accepte l’origine IA.
- Pas d’effet sur Asset Store, bibliothèques officielles, index, resolver,
  validation, publication immuable ou transferts `.kiparts`. Les profils/historiques
  M10/M11 restent locaux comme précédemment ; ils ne voyagent pas dans M8 v1.

## Vérification et limites

Les trois contrats HTTP sont vérifiés avec réponses et transports simulés ; l’UI
est vérifiée hors ligne, également nativement sur macOS et à trois tailles.
**Aucun appel live Gemini/OpenAI ni inférence sur un Ollama installé n’a été effectué**
pendant ce checkpoint. Une clé, un modèle accessible et une exécution autorisée
restent nécessaires pour qualifier le service réellement choisi.
Pas de chatbot, conversation persistante, retrieval automatique, lecture automatique
PDF, estimation fiable de confiance ou validation électrique. M12 non démarrée.

## FabParts Tauri — TECH-06C

Les mêmes services M11 sont maintenant accessibles depuis la fiche complète,
section **Assistance IA · facultative**, et **Paramètres → Assistance IA — Facultative**.
Le contexte n'est jamais déduit d'un PDF. Préparer, autoriser l'envoi et accepter
les champs sont trois actions distinctes. Le JSON utilisateur exact et la destination
réelle sont affichés avant l'autorisation, sans identifiant, historique ou fichier
ajouté. Le modèle doit déjà être disponible chez le fournisseur ou dans Ollama.

Le host conserve `env_clear()` et transmet seulement les deux variables M11
GEMINI_API_KEY / KIPART_AI_API_KEY, jamais au frontend. Il faut relancer FabParts
depuis l'environnement configuré ; l'interface n'enregistre pas les clés.
« Configuration prête » signale la configuration/clé locale, sans sonde réseau ni
garantie de disponibilité du modèle. Pas d'inférence au démarrage ou à l'ingestion.

L'analyse utilise un worker borné, la navigation reste disponible. Modifier,
ignorer ou quitter révoque la session ; une réponse retardée est rejetée. Avant
acceptation, Python revérifie composant, configuration et révision M10. Tous les
champs commencent décochés ; seuls les champs explicitement acceptés et leur
provenance sont persistés atomiquement. Les derniers événements sont consultables
sur place. Le transport ne réessaie pas automatiquement une acceptation incertaine :
recharger la fiche/l'historique avant de décider à nouveau.

La qualification TECH-06C (simulations, inspection native et limites des essais
réels) est détaillée dans [le rapport](FABPARTS_2_TECH_06C.md). Les constatations
historiques M11 ci-dessus ne constituent pas une qualification live d'un compte
Gemini/OpenAI ou d'un modèle Ollama installé.
