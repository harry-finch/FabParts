import { i18n } from '../../fabparts-ux/src/lib/i18n.svelte';
const fr = {
  qualificationShort:'Non évaluée',
  copyDirectory:'Dossier de la copie TECH-01',
  copy:'Copie du catalogue · lecture seule', all:'Tous les composants', libraries:'Bibliothèques', categories:'Catégories',
  allCategories:'Toutes les catégories', search:'Rechercher un composant…', allStates:'Tous les états métier', allPackages:'Tous les boîtiers',
  component:'Composant', package:'Boîtier', state:'État métier', draft:'Brouillon', identified:'Identifié', deprecated:'Obsolète',
  loading:'Chargement…', starting:'Démarrage du moteur…', failed:'Moteur indisponible', restart:'Redémarrer le moteur',
  empty:'Aucun composant', emptyHint:'Cette bibliothèque ou cette recherche ne contient aucun composant.', clear:'Effacer les filtres',
  select:'Sélectionnez un composant', details:'Ouvrir la fiche', back:'Bibliothèques', resources:'Ressources',
  noResource:'Aucune ressource associée', preview:'Aperçu non connecté dans TECH-01', qualification:'Qualification technique non évaluée dans TECH-01',
  associated:'Associée', selected:'Sélectionnée', external:'Référence KiCad externe', unknown:'Non renseigné',
  properties:'Propriétés', manufacturer:'Fabricant', category:'Catégorie', technical:'Détails techniques',
  previous:'Précédent', next:'Suivant', closeInspector:'Masquer les détails', openInspector:'Afficher les détails',
  readonly:'Consultation seule. Ajout, modification et publication hors périmètre TECH-01.',
  add:'Ajouter', noWrite:'Ajout indisponible dans ce prototype en lecture seule', documents:'Documents',
  symbol:'Symbole', footprint:'Empreinte', model:'Modèle 3D', datasheet:'Datasheet', missing:'Non associée',
  noPreview:'Les métadonnées ci-dessous proviennent du moteur. Aucun aperçu de démonstration.',
  resize:'Redimensionner les détails', results:'résultat(s)', source:'Origine', file:'Fichier', hash:'SHA-256',
};
const en: Record<keyof typeof fr,string> = {
  qualificationShort:'Not evaluated',
  copyDirectory:'TECH-01 copy directory',
  copy:'Catalogue copy · read only',all:'All components',libraries:'Libraries',categories:'Categories',allCategories:'All categories',
  search:'Search components…',allStates:'All business states',allPackages:'All packages',component:'Component',package:'Package',state:'Business state',
  draft:'Draft',identified:'Identified',deprecated:'Deprecated',loading:'Loading…',starting:'Starting engine…',failed:'Engine unavailable',restart:'Restart engine',
  empty:'No components',emptyHint:'This library or search contains no components.',clear:'Clear filters',select:'Select a component',details:'Open details',back:'Libraries',resources:'Resources',
  noResource:'No associated resource',preview:'Preview not connected in TECH-01',qualification:'Technical qualification not evaluated in TECH-01',associated:'Associated',selected:'Selected',external:'External KiCad reference',unknown:'Not specified',
  properties:'Properties',manufacturer:'Manufacturer',category:'Category',technical:'Technical details',previous:'Previous',next:'Next',closeInspector:'Hide details',openInspector:'Show details',
  readonly:'Read only. Adding, editing and publishing are outside TECH-01.',add:'Add',noWrite:'Adding is unavailable in this read-only prototype',documents:'Documents',symbol:'Symbol',footprint:'Footprint',model:'3D model',datasheet:'Datasheet',missing:'Not associated',
  noPreview:'The metadata below comes from the engine. No demonstration preview.',resize:'Resize details',results:'result(s)',source:'Origin',file:'File',hash:'SHA-256',
};
export const text = (key: keyof typeof fr) => (i18n.locale === 'fr' ? fr : en)[key];
export const stateLabel = (s: string) => text(s === 'DRAFT' ? 'draft' : s === 'IDENTIFIED' ? 'identified' : 'deprecated');
export const roles = ['SYMBOL','FOOTPRINT','MODEL_3D','DATASHEET'];
export const roleLabel = (r: string) => text(r === 'SYMBOL' ? 'symbol' : r === 'FOOTPRINT' ? 'footprint' : r === 'MODEL_3D' ? 'model' : 'datasheet');
