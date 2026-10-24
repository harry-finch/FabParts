// Identité de l'application : nom affiché et préfixe des clés de stockage
// local (`fabparts-ux.theme.v1`, `fabparts-ux.section.plate`…). Remplacer `fabparts-ux`
// par l'identifiant de l'application, en minuscules, sans espace.

export const APP_ID = "fabparts-ux";
export const APP_NAME = "FabParts";

/** Clé du stockage local, préfixée par l'application. */
export const storageKey = (key: string) => `${APP_ID}.${key}`;
