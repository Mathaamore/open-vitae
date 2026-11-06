# Open Vitæ — identité

Direction A validée le 6 novembre 2026. Nom affiché **Open Vitæ**, logotype en minuscules **open vitæ**, nom technique **open-vitae**. Le symbole æ relie deux lettres tout en gardant leur lecture. Les originaux SVG sont vectoriels, sans police à installer.

## Choisir un fichier

- `horizontal.svg` : symbole et nom, sur fond blanc ou clair. Largeur minimale 180 px.
- `wordmark.svg` : nom seul, notamment à côté de l’icône dans l’app. Minimum 112 px.
- `stacked.svg` : composition sur deux lignes. Minimum 160 px.
- `symbol.svg` et `symbol-small.svg` : symbole seul. Minimum 16 px. Le petit fichier conserve le même dessin, déjà lisible à cette taille ; pas de variante simplifiée distincte.
- `symbol-white.svg` et `horizontal-white.svg` : fonds sombres. Versions noires également fournies.
- `app-icon.png` / `app-icon.svg` : icône Mac de 1024 px, avec marges transparentes et fond arrondi.
- `web-icons/` : favicon ICO 16/32/48 px, icônes web et Apple. `favicon.svg` fournit une tuile claire pour les barres d’onglets claires ou sombres.
- `presentation.html` et `presentation/` : planche d’identité et aperçus fictifs ; aucun domaine, compte social ou site présenté n’est réservé ou publié.

## Couleurs et typographie

| Couleur | HEX | RGB | Usage |
|---|---|---|---|
| Vert profond | #214B40 | 33, 75, 64 | Logo, actions principales |
| Poire | #D8EDA2 | 216, 237, 162 | Fond de l’icône et petits repères |
| Papier | #FFFFFF | 255, 255, 255 | Fond principal |
| Encre | #24282E | 36, 40, 46 | Texte de l’interface |

Contraste vert sur poire : 7,72:1 ; vert sur blanc : 9,79:1. Ces valeurs utilisent la luminance relative sRGB WCAG. Sur un fond sombre, employer une version blanche. Pas de teinte poire seule sur blanc pour un petit texte.

Le lettrage part de Geist variable (poids demandé 580), avec espacement optique et un æ redessiné, puis converti en tracés. L’interface utilise Geist. Licence de police SIL OFL jointe : `Geist-OFL.txt`. Les SVG/PNG du logo original sont distribués avec le code de l’app sous MIT ; conserver les notices des polices. Palette numérique RGB ; pas de profil CMYK ni de référence Pantone certifiée.

## Espace et intégrité

Garder autour du dessin une zone libre d’au moins la largeur de sa barre centrale, soit environ 1/8 de la largeur du symbole. Les marges transparentes des fichiers ne remplacent pas cette zone à proximité d’un autre élément.

Conserver les proportions et les couleurs. Ne pas étirer, incliner, ajouter d’ombre au dessin, fermer ses contreformes ou recomposer les lettres. Utiliser le fichier fourni plutôt que retaper le nom pour recréer le logo. Les deux formes pleines du æ se chevauchent à leur jonction sans trait de séparation ; une découpe physique demanderait une union des tracés dans un éditeur vectoriel.

## Vérification et limites

SVG audités : pas de texte actif, raster ou filtre ; symboles à 16/32/64 px, noir/blanc inversé, flou, rotation et contextes inspectés. L’icône de l’app et le lettrage intégré ont été contrôlés sur ordinateur et mobile. Les aperçus d’identité servent à montrer les usages, sans prétendre que ces pages sont publiées.

Le préfixe Open ne garantit pas une disponibilité juridique. Des produits Vitæ/Vitae liés à l’emploi existent ; aucune recherche de marque exhaustive, réservation de domaine ou publication effectuée. Le nom du paquet et son affichage changent, mais l’identifiant macOS, le trousseau et le dossier local Candidatures restent stables pour préserver les données.
