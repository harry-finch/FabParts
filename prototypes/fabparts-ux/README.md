# FabParts — UX Prototype 02

Prototype isolé de l’application Python. **Données et ressources de démonstration uniquement.**

```sh
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Ouvrir http://127.0.0.1:5173 dans une fenêtre desktop. `npm run check` vérifie les
sources, `npm test` exécute les 12 tests de préparation (vérifiés sous Node 26),
`npm run build` compile l’application statique, `npm run standalone`
génère également `dist/preview.html` sans dépendance externe à l’exécution.

Les captures et comptes rendus internes ne sont pas distribués. Les opérations et ressources restent simulées.

Le catalogue de démonstration reste dans le stockage du navigateur, sous
`fabparts-ux.*`. Paramètres du prototype → Réinitialiser la démonstration restaure
les exemples. Aucune base SQLite, configuration KiCad ou connexion fournisseur
n’est utilisée. Les fichiers déposés ne sont représentés que par leurs noms.

Les primitives et tokens viennent de `.agents/skills/fab-design-system/assets/starter/`.
Le logo est la copie inchangée de `src/kipartmanager/ui/branding/source/app_icon.svg`.
