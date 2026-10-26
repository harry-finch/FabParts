import type {AIDiagnostic} from './assistance';
// Diagnostics allowlisted in Python; never render a provider body or exception text.
const messages:Record<string,readonly [string,string]>={
 missing_key:['Clé API absente du moteur. Relancez FabParts depuis le terminal où la variable de clé est définie.','API key missing in the engine. Relaunch FabParts from the terminal where the key variable is set.'],
 authentication:['Authentification refusée par le fournisseur. Vérifiez la clé API et relancez FabParts si vous la modifiez.','Authentication rejected by the provider. Check the API key and relaunch FabParts if you change it.'],
 permission:['Accès refusé par le fournisseur. Vérifiez la clé, les droits du compte et l’accès au modèle.','Access denied by the provider. Check the key, account permissions and model access.'],
 model_or_endpoint:['Modèle ou endpoint introuvable. Vérifiez le nom exact du modèle et l’URL dans Paramètres.','Model or endpoint not found. Check the exact model name and URL in Settings.'],
 rate_limit:['Limite de requêtes ou quota atteint. Vérifiez les limites du compte avant de réessayer manuellement.','Request limit or quota reached. Check account limits before trying again manually.'],
 bad_request:['Demande refusée comme invalide. Vérifiez le fournisseur, l’endpoint, le modèle et leur compatibilité. Ce statut ne permet pas de confirmer la validité de la clé.','Request rejected as invalid. Check the provider, endpoint, model and compatibility. This status does not confirm that the key is valid.'],
 provider_unavailable:['Le fournisseur rencontre une erreur serveur. Réessayez plus tard manuellement.','The provider encountered a server error. Try again manually later.'],
 http_error:['Le fournisseur a refusé la demande. Vérifiez sa configuration et la disponibilité du service.','The provider rejected the request. Check its configuration and service availability.'],
 network:['Connexion au fournisseur impossible (réseau, DNS ou TLS). Vérifiez la connexion, l’endpoint ou le service Ollama local.','Cannot connect to the provider (network, DNS or TLS). Check the connection, endpoint or local Ollama service.'],
 timeout:['Le fournisseur n’a pas répondu dans le délai prévu. Vérifiez sa disponibilité ou la charge du modèle avant de réessayer manuellement.','The provider did not respond within the time limit. Check its availability or model load before trying again manually.'],
 redirect:['Redirection refusée pour protéger la clé. Configurez directement l’endpoint final autorisé.','Redirect rejected to protect the key. Configure the authorised final endpoint directly.'],
 too_large:['Réponse reçue trop volumineuse ; elle a été rejetée. Réduisez le contexte ou vérifiez le modèle.','The response was too large and was rejected. Shorten the context or check the model.'],
 blocked:['Le fournisseur a bloqué la demande ou la réponse. Revoyez le contexte et les règles du fournisseur.','The provider blocked the request or response. Review the context and provider policies.'],
 incomplete:['Réponse interrompue par la limite de sortie du modèle ; aucune proposition utilisable. Réduisez le contexte ou choisissez un modèle adapté.','Response stopped at the model output limit; no usable suggestions. Shorten the context or choose a suitable model.'],
 invalid_response:['Réponse reçue, mais son JSON ou ses champs ne respectent pas le format attendu. Vérifiez la compatibilité du modèle.','A response was received, but its JSON or fields do not match the required format. Check model compatibility.'],
 no_suggestions:['Le fournisseur a répondu sans suggestion exploitable. Ajoutez des informations au contexte ou continuez manuellement.','The provider responded without usable suggestions. Add information to the context or continue manually.'],
 unknown:['Échec de l’analyse sans diagnostic identifiable. Vérifiez les paramètres du fournisseur ou continuez manuellement.','Analysis failed without an identifiable diagnosis. Check provider settings or continue manually.'],
};
export function assistanceError(diagnostic:AIDiagnostic|null,locale:string):string{
 const code=diagnostic?.code;
 const message=(code&&Object.hasOwn(messages,code)?messages[code]:messages.unknown)[locale==='fr'?0:1];
 const status=diagnostic?.http_status;
 const http=typeof status==='number'&&Number.isInteger(status)&&status>=100&&status<=599?` (HTTP ${status})`:'';
 return message+http+' '+(locale==='fr'?'Aucun champ enregistré. Aucun nouvel essai automatique.':'No fields saved. No automatic retry.');
}
