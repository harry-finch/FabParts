import { i18n } from '../../fabparts-ux/src/lib/i18n.svelte';
const fr = {
  modelPan:'Déplacer le modèle',modelView:'Vue',modelIso:'Isométrique',modelTop:'Dessus',modelBottom:'Dessous',modelFront:'Face',modelBack:'Arrière',
  modelZoomOut:'Zoom arrière 3D',modelZoomIn:'Zoom avant 3D',modelFit:'Cadrer le modèle',modelCanvas:'Aperçu 3D interactif',
  modelHelp:'Glisser : rotation · clic droit ou Maj + glisser : pan · molette : zoom',
  modelMillimetres:'Coordonnées en mm, sans valeur de mesure certifiée',modelSourceUnits:'WRL : unités du fichier, échelle physique non déduite',
  modelContextLost:'Contexte WebGL perdu. Rouvrez l’aperçu si la restauration échoue.',modelWebglUnavailable:'Rendu WebGL indisponible sur cette machine.',

  qualificationShort:'Non évaluée',
  copyDirectory:'Dossier de la copie TECH-01',
  copy:'Copie du catalogue · lecture seule', all:'Tous les composants', libraries:'Bibliothèques', categories:'Catégories',
  allCategories:'Toutes les catégories', search:'Rechercher un composant…', allStates:'Tous les états métier', allPackages:'Tous les boîtiers',
  component:'Composant', package:'Boîtier', state:'État métier', draft:'Brouillon', identified:'Identifié', deprecated:'Obsolète',
  loading:'Chargement…', starting:'Démarrage du moteur…', failed:'Moteur indisponible', restart:'Redémarrer le moteur',
  empty:'Aucun composant', emptyHint:'Cette bibliothèque ou cette recherche ne contient aucun composant.', clear:'Effacer les filtres',
  select:'Sélectionnez un composant', details:'Ouvrir la fiche', back:'Bibliothèques', resources:'Ressources',
  noResource:'Aucune ressource associée', preview:'Consulter les aperçus dans la fiche', qualification:'Qualification technique non évaluée dans ce prototype',
  associated:'Associée', selected:'Sélectionnée', external:'Référence KiCad externe', unknown:'Non renseigné',
  properties:'Propriétés', manufacturer:'Fabricant', category:'Catégorie', technical:'Détails techniques',
  previous:'Précédent', next:'Suivant', closeInspector:'Masquer les détails', openInspector:'Afficher les détails',
  readonly:'Consultation seule. Les modifications sont désactivées.',
  add:'Ajouter', noWrite:'Ajout indisponible en lecture seule', documents:'Documents',
  symbol:'Symbole', footprint:'Empreinte', model:'Modèle 3D', datasheet:'Datasheet', missing:'Non associée',
  noPreview:'Les métadonnées ci-dessous proviennent du moteur. Aucun aperçu de démonstration.',
  resize:'Redimensionner les détails', results:'résultat(s)', source:'Origine', file:'Fichier', hash:'SHA-256',
};
const en: Record<keyof typeof fr,string> = {
  modelPan:'Pan model',modelView:'View',modelIso:'Isometric',modelTop:'Top',modelBottom:'Bottom',modelFront:'Front',modelBack:'Back',
  modelZoomOut:'Zoom out 3D',modelZoomIn:'Zoom in 3D',modelFit:'Fit model',modelCanvas:'Interactive 3D preview',
  modelHelp:'Drag: orbit · right button or Shift + drag: pan · wheel: zoom',
  modelMillimetres:'Coordinates in mm, not certified measurements',modelSourceUnits:'WRL: source units, physical scale not inferred',
  modelContextLost:'WebGL context lost. Reopen the preview if restoration fails.',modelWebglUnavailable:'WebGL rendering is unavailable on this machine.',

  qualificationShort:'Not evaluated',
  copyDirectory:'TECH-01 copy directory',
  copy:'Catalogue copy · read only',all:'All components',libraries:'Libraries',categories:'Categories',allCategories:'All categories',
  search:'Search components…',allStates:'All business states',allPackages:'All packages',component:'Component',package:'Package',state:'Business state',
  draft:'Draft',identified:'Identified',deprecated:'Deprecated',loading:'Loading…',starting:'Starting engine…',failed:'Engine unavailable',restart:'Restart engine',
  empty:'No components',emptyHint:'This library or search contains no components.',clear:'Clear filters',select:'Select a component',details:'Open details',back:'Libraries',resources:'Resources',
  noResource:'No associated resource',preview:'View previews in component details',qualification:'Technical qualification not evaluated in this prototype',associated:'Associated',selected:'Selected',external:'External KiCad reference',unknown:'Not specified',
  properties:'Properties',manufacturer:'Manufacturer',category:'Category',technical:'Technical details',previous:'Previous',next:'Next',closeInspector:'Hide details',openInspector:'Show details',
  readonly:'Read only. Changes are disabled.',add:'Add',noWrite:'Adding is unavailable in read-only mode',documents:'Documents',symbol:'Symbol',footprint:'Footprint',model:'3D model',datasheet:'Datasheet',missing:'Not associated',
  noPreview:'The metadata below comes from the engine. No demonstration preview.',resize:'Resize details',results:'result(s)',source:'Origin',file:'File',hash:'SHA-256',
};
export const text = (key: keyof typeof fr) => (i18n.locale === 'fr' ? fr : en)[key];
export const stateLabel = (s: string) => text(s === 'DRAFT' ? 'draft' : s === 'IDENTIFIED' ? 'identified' : 'deprecated');
export const roles = ['SYMBOL','FOOTPRINT','MODEL_3D','DATASHEET'];
export const roleLabel = (r: string) => text(r === 'SYMBOL' ? 'symbol' : r === 'FOOTPRINT' ? 'footprint' : r === 'MODEL_3D' ? 'model' : 'datasheet');

export const tr = (fr:string,en:string) => i18n.locale==='fr' ? fr : en;
