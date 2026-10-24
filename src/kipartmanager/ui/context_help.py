"""Short explanations shared by resource inspection and catalogue forms."""

HELP = {
    "package": "Boîtier physique du composant. Ses footprints et modèles 3D peuvent être "
    "partagés par plusieurs références de composants.",
    "footprint": "Empreinte sur le circuit imprimé : position des pads, sérigraphie et "
    "zone d’encombrement (courtyard). Vérifiez dimensions et numérotation avant utilisation.",
    "symbol": "Représentation électrique du composant : broches, noms et numéros. "
    "Les unités sont les différentes parties d’un symbole ; les vues sont ses représentations.",
    "asset": "Une ressource est un symbole, footprint, modèle 3D ou PDF. Un fichier géré est "
    "conservé dans le stockage local ; sa provenance décrit d’où il vient.",
    "official": "Une ressource officielle KiCad reste dans votre installation, en lecture seule. "
    "L’index permet de la retrouver ; il ne la copie pas dans votre catalogue.",
    "inventory": "Un inventaire regroupe les composants que vous possédez et leurs quantités. "
    "Il est indépendant des bibliothèques exposées à KiCad.",
    "library": "Une bibliothèque (collection) sélectionne les composants à exposer à KiCad. "
    "L’ajout d’un composant ne publie pas encore ses fichiers.",
    "publication": "Une publication est une version figée de votre bibliothèque validée. "
    "Le mode portable copie les ressources choisies avec des liens utilisables sur un autre poste.",
    "pdf": "Document conservé localement. L’aperçu donne accès à toutes les pages ; "
    "les informations de provenance sont disponibles sous le document.",
}
