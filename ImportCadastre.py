import requests
import os
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsLayerTreeGroup,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform
)

# === 1. Récupération des coordonnées EPSG:4326 du centre du canevas ===
canvas = iface.mapCanvas()
center = canvas.extent().center()

# Transformation des coordonnées en EPSG:4326 (WGS84)
crsSrc = canvas.mapSettings().destinationCrs()  # CRS du projet
crsDest = QgsCoordinateReferenceSystem("EPSG:4326")  # WGS84
transform = QgsCoordinateTransform(crsSrc, crsDest, QgsProject.instance())

center_WGS84 = transform.transform(center)
latitude, longitude = center_WGS84.y(), center_WGS84.x()

# === 2. Requête API pour récupérer les informations de la commune ===
api_url = f"https://geo.api.gouv.fr/communes?lat={latitude}&lon={longitude}&zone=metro&type=commune-actuelle&fields=nom,code,departement&format=json&geometry=centre"

response = requests.get(api_url)
if response.status_code == 200 and response.json():
    data = response.json()[0]  # Prend la première commune trouvée
    communeINSEE = data["code"]
    communeNom = data["nom"]
    départementNom = data["departement"]["nom"]
    départementCode = data["departement"]["code"]
    print(f"Commune trouvée : {communeNom} ({communeINSEE}), Département : {départementNom} ({départementCode})")
else:
    print("❌ Erreur : Impossible de récupérer les informations de la commune.")
    exit()

# === 3. Définition des URLs et chargement des couches ===
base_url = f"https://cadastre.data.gouv.fr/bundler/cadastre-etalab/communes/{communeINSEE}/geojson/"
layers_info = {
    "sections": "sections",
    "batiments": "batiments",
    "parcelles": "parcelles",
    "communes": "communes",
}

# === 4. Création des groupes thématiques dans QGIS ===
project = QgsProject.instance()
root = project.layerTreeRoot()

# Vérifier ou créer le groupe principal "Cadastre"
cadastre_group = root.findGroup("Cadastre")
if not cadastre_group:
    cadastre_group = root.addGroup("Cadastre")

# Vérifier ou créer le groupe pour le département (ex: "13 - Bouches-du-Rhône")
department_group_name = f"{départementCode} - {départementNom}"
department_group = cadastre_group.findGroup(department_group_name)
if not department_group:
    department_group = cadastre_group.addGroup(department_group_name)

# Créer le groupe pour la commune sous le département (ex: "13001 - Marseille")
commune_group_name = f"{communeINSEE} - {communeNom}"
commune_group = department_group.addGroup(commune_group_name)

commune_groupe = root.findGroup(commune_group_name)
if commune_groupe:
    commune_groupe.setExpanded(False)
else:
    print(f"Groupe '{commune_groupe}' non trouvé.")

# === 5. Chargement des couches dans l'ordre souhaité ===
layer_order = ["batiments", "communes", "sections", "parcelles"]

loaded_layers = {}
for layer_name in layer_order:
    url = base_url + layers_info[layer_name]
    layer = QgsVectorLayer(url, f"{layer_name.capitalize()} - {communeNom}", "ogr")
    
    if not layer.isValid():
        print(f"⚠️ Erreur : Impossible de charger la couche {layer_name}.")
        continue
    
    # Ajouter la couche au projet
    QgsProject.instance().addMapLayer(layer, False)
    commune_group.addLayer(layer)
    loaded_layers[layer_name] = layer

# === 6. Copier les styles des couches depuis le dossier Cadastre ===
project_path = QgsProject.instance().fileName()
if not project_path:
    print("❌ Erreur : Le fichier projet QGIS doit être enregistré pour copier les styles.")
else:
    # Déterminer le chemin du dossier "Cadastre" dans le même dossier que le projet
    project_directory = os.path.dirname(project_path)
    style_directory = os.path.join(project_directory, "Cadastre")
    
    if not os.path.exists(style_directory):
        print(f"❌ Erreur : Le dossier 'Cadastre' n'existe pas dans {project_directory}.")
    else:
        for layer_name, layer in loaded_layers.items():
            style_path = os.path.join(style_directory, f"{layer_name}.qml")
            
            if os.path.exists(style_path):
                layer.loadNamedStyle(style_path)
                layer.triggerRepaint()
                print(f"✅ Style appliqué pour la couche {layer_name}.")
            else:
                print(f"⚠️ Avertissement : Le style {layer_name}.qml est manquant dans {style_directory}.")

# === 7. Masquer la couche "Cadastre PCI Express" si elle existe ===
cadastre_express_layer = QgsProject.instance().mapLayersByName("Cadastre PCI Express")
if cadastre_express_layer:
    for layer in cadastre_express_layer:
        node = root.findLayer(layer.id())
        if node:
            node.setItemVisibilityChecked(False)
            print("✅ La couche 'Cadastre PCI Express' a été masquée.")
else:
    print("ℹ️ La couche 'Cadastre PCI Express' n'existe pas dans le projet.")

print("🎯 Toutes les couches ont été chargées et classées avec succès.")
