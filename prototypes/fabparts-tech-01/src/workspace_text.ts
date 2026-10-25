import { i18n } from '../../fabparts-ux/src/lib/i18n.svelte';
const fr={settings:'Paramètres et données',back:'Retour au catalogue',active:'Espace de travail actif',
 personal:'Espace personnel',backups:'Dossier des sauvegardes',save:'Sauvegarder mes données',
 restore:'Restaurer une sauvegarde',choose:'Choisir une sauvegarde…',confirm:'Restaurer dans un nouvel espace',
 help:'La sauvegarde comprend le catalogue, les fichiers, la configuration et les publications. Les sauvegardes précédentes sont conservées.',
 restoreHelp:'Choisissez un dossier de sauvegarde FabParts. Son intégrité sera vérifiée. La restauration conserve les données actuelles et prépare un nouvel espace.',
 verified:'Sauvegarde vérifiée',files:'fichier(s)',date:'Créée le',schema:'Schéma',
 busy:'Opération en cours…',saved:'Sauvegarde complète créée et vérifiée.',
 restored:'Restauration vérifiée. Redémarrez le moteur pour utiliser le nouvel espace. Vos données précédentes sont conservées.',
 restart:'Redémarrer le moteur',failed:'Opération impossible. Les données actuelles sont conservées. Vérifiez la sauvegarde, les permissions et l’espace disque.',
 uncertain:'Si une restauration a été interrompue, vérifiez l’espace actif après redémarrage avant de recommencer.',
 loading:'Lecture de l’espace…',unavailable:'Espace personnel indisponible, déjà ouvert ou incompatible. Fermez l’autre instance et vérifiez les permissions.'};
const en:Record<keyof typeof fr,string>={settings:'Settings and data',back:'Back to catalogue',active:'Active workspace',
 personal:'Personal workspace',backups:'Backup folder',save:'Back up my data',restore:'Restore a backup',choose:'Choose backup…',confirm:'Restore into a new workspace',
 help:'Backups include the catalogue, files, configuration and publications. Previous backups are retained.',
 restoreHelp:'Choose a FabParts backup folder. Its integrity will be checked. Restoration retains current data and prepares a new workspace.',
 verified:'Backup verified',files:'file(s)',date:'Created on',schema:'Schema',busy:'Operation in progress…',saved:'Complete backup created and verified.',
 restored:'Restoration verified. Restart the engine to use the new workspace. Your previous data is retained.',restart:'Restart engine',
 failed:'Operation failed. Current data is retained. Check the backup, permissions and available disk space.',
 uncertain:'If a restore was interrupted, check the active workspace after restarting before trying again.',loading:'Loading workspace…',
 unavailable:'Personal workspace unavailable, already open or incompatible. Close the other instance and check permissions.'};
export function workspaceText(key:keyof typeof fr):string{return(i18n.locale==='en'?en:fr)[key];}
