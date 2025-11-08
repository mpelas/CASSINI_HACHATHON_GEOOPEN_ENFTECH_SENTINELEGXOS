import functions_framework
import requests
import json
import hashlib
import io
import simplekml  # For KML generation
from shapely.geometry import Point, mapping, shape
from shapely.ops import cascaded_union, transform
from shapely import wkt
from google.cloud import storage

from pyproj import CRS, Transformer
import math

from flask import jsonify

# ======================================================================
# --- CONSTANTS ---
# ======================================================================


# Constants for the main Cloud Function (check_for_changes)
WASTEWATER_API_URL = "https://astikalimata.ypeka.gr/api/query/wastewatertreatmentplants"
GCS_BUCKET_NAME = "mpelas-wastewater-bucket" # Primary data bucket (for GeoJSON source/hash)
PERIFEREIES_GEOJSON_PATH = "perifereiesWGS84.geojson"
LAST_HASH_FILE_PATH = "wastewater_data_hash.txt"
OUTPUT_GEOJSON_PATH = "no_swim_zones/wastewater_no_swim_zones.geojson"
BUFFER_DISTANCE_METERS = 200
#
# Constants for the KML/GCS Sync 
GEOJSON_PATH = OUTPUT_GEOJSON_PATH # Same file path
# New Destination Bucket for the Public KML/SPA
PUBLIC_HOSTING_BUCKET = "wastewater_plants_spa"
# Original KML Filename (remains the same)
KML_FILENAME = "wastewater_no_swim_zones.kml"


# Define coordinate reference systems
WGS84_CRS = CRS("EPSG:4326")        # Standard GPS coordinates (Degrees)
GREEK_GRID_CRS = CRS("EPSG:2100")   # Greek Grid for accurate meters (Meters)

# Create transformers (always_xy=True ensures correct (lon, lat) or (east, north) order)
transformer_to_greek_grid = Transformer.from_crs(WGS84_CRS, GREEK_GRID_CRS, always_xy=True).transform
transformer_to_wgs84 = Transformer.from_crs(GREEK_GRID_CRS, WGS84_CRS, always_xy=True).transform

# ======================================================================
# --- HELPER FUNCTIONS (GCS/Geospatial) ---
# ======================================================================

def get_gcs_blob(bucket_name, blob_name):
    """Retrieves a blob from Google Cloud Storage."""
    # Instantiate client without credentials to use Application Default Credentials
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    return bucket.blob(blob_name)

def load_perifereies_data(bucket_name, file_path):
    """Loads and parses the large perifereies GeoJSON file from GCS."""
    try:
        blob = get_gcs_blob(bucket_name, file_path)
        geojson_data = blob.download_as_text()
        perifereies_features = json.loads(geojson_data)
        perifereies_geometries = [
            shape(f['geometry']) for f in perifereies_features.get('features', [])
        ]
        print("====DIABASA tis perifereies perifereiesWGS84.geojson")
        return perifereies_geometries
    except Exception as e:
        print(f"Error loading perifereies GeoJSON: {e}")
        return None

def calculate_new_zones(perifereies_geometries, wastewater_data):
    """
    Performs the core geospatial analysis: buffering, union, and difference.
    Returns a list of GeoJSON features.
    """
    print("Starting geospatial analysis...")
    no_swim_zones_with_metadata = []

    if not perifereies_geometries:
        print("Perifereies geometries are empty. Cannot calculate differences.")
        return []

    # Create the single, unified geometry for the difference operation
    unified_perifereies = cascaded_union(perifereies_geometries)
    print("Perifereies unified successfully.")

    if isinstance(wastewater_data, dict) and 'features' in wastewater_data:
        features_to_process = wastewater_data['features']
    elif isinstance(wastewater_data, list):
        features_to_process = wastewater_data
    else:
        print("Invalid wastewater data format.")
        return []

    for plant_feature in features_to_process:
        try:
            props = plant_feature.get('properties', plant_feature)
            
            metadata = {
                'code': props.get('code'),
                'name': props.get('name'),
                'receiverName': props.get('receiverName'),
                'receiverNameEn': props.get('receiverNameEn'),
                'receiverWaterType': props.get('receiverWaterType'),
                'latitude': props.get('latitude'),
                'longitude': props.get('longitude')
            }

            receiver_location_wkt = props.get('receiverLocation')
            longitude = props.get('longitude')
            latitude = props.get('latitude')

            point_wgs84 = None
            
            # 1. Determine the discharge point
            if receiver_location_wkt:
                try:
                    point_wgs84 = wkt.loads(receiver_location_wkt)
                except Exception as e:
                    print(f"Error parsing WKT for plant '{metadata.get('name')}': {e}. Falling back to main coordinates.")
            
            if point_wgs84 is None and longitude is not None and latitude is not None:
                point_wgs84 = Point(longitude, latitude)
            
            if point_wgs84 is None or point_wgs84.is_empty:
                print(f"Skipping plant '{metadata.get('name')}' due to missing or invalid coordinates.")
                continue

            # 2. Project the WGS84 point to the metric Greek Grid (EPSG:2100)
            point_greek_grid = transform(transformer_to_greek_grid, point_wgs84)

            # 3. Buffer the point in meters
            buffered_point_greek_grid = point_greek_grid.buffer(BUFFER_DISTANCE_METERS)
            
            # 4. Project the buffer back to WGS84 
            buffered_point_wgs84 = transform(transformer_to_wgs84, buffered_point_greek_grid)
            
            # 5. Perform Difference: Find the part of the buffer that is *not* on the mainland
            danger_zone = buffered_point_wgs84.difference(unified_perifereies)
            
            if not danger_zone.is_empty:
                # Store as a GeoJSON Feature object
                # Adding 'location' and 'compliance' keys for KML conversion compatibility
                kml_properties = {
                    'location': metadata.get('name', props.get('name') + " " + props.get('code')  ),
                    # Assuming a 'is_compliant' key or defaulting to True if not present in source data
                    'Column1.compliance': props.get('is_compliant', True), 
                    'details': f"Code: {metadata.get('code', 'N/A')}. Receiver: {metadata.get('receiverName', 'N/A')}",
                    **metadata
                }
                no_swim_zones_with_metadata.append({
                    "type": "Feature",
                    "geometry": mapping(danger_zone),
                    "properties": kml_properties
                })
        
        except Exception as e:
            print(f"Skipping plant due to an error processing its data: {e}")
            continue

    print(f"Geospatial analysis complete. Found {len(no_swim_zones_with_metadata)} no-swim zones.")
    return no_swim_zones_with_metadata

# ======================================================================
# --- HELPER FUNCTIONS (KML/GCS) ---
# ======================================================================

def get_geojson_from_gcs():
    """Download GeoJSON from the primary GCS data bucket."""
    # Instantiate client without credentials to use Application Default Credentials
    storage_client = storage.Client()
    # Use the primary data bucket (GCS_BUCKET_NAME) to read the GeoJSON
    bucket = storage_client.bucket(GCS_BUCKET_NAME) 
    blob = bucket.blob(GEOJSON_PATH)
    geojson_data = json.loads(blob.download_as_text())
    return geojson_data

def geojson_to_kml(geojson_data):
    """Convert GeoJSON to KML format"""
    kml = simplekml.Kml()
    
    for feature in geojson_data.get('features', []):
        geometry = feature.get('geometry', {})
        properties = feature.get('properties', {})
        geom_type = geometry.get('type')
        coordinates = geometry.get('coordinates', [])
        
        # Get properties for styling and info
        location = properties.get('location', 'Unknown Location')
        compliance = properties.get('Column1.compliance', None)
        details = properties.get('details', 'No details available')
        
        # Create description
        description = f"""
        <![CDATA[
        <b>Name:</b> {properties.get('name', 'N/A')}<br>
        <b>Code:</b> {properties.get('code', 'N/A')}<br>
        <b>Receiver:</b> {properties.get('receiverName', 'N/A')}<br>
        <b>Compliance:</b> {'⚠️ NON-COMPLIANT' if compliance is False else '✓ Compliant'}<br>
        <b>Details:</b> {details}
        ]]>
        """
        
        # Determine color based on compliance
        if compliance is False:
            color = simplekml.Color.red
        else:
            # Semi-Transparent Blue
            color = simplekml.Color.changealphaint(150, simplekml.Color.blue) 
        
        # Add geometry to KML
        if geom_type == 'Polygon':
            coords = coordinates[0]
            kml_coords = [(coord[0], coord[1]) for coord in coords]
            
            pol = kml.newpolygon(name=location, description=description)
            pol.outerboundaryis = kml_coords
            pol.style.polystyle.color = color
            pol.style.polystyle.fill = 1
            pol.style.polystyle.outline = 1
            pol.style.linestyle.color = simplekml.Color.white
            pol.style.linestyle.width = 2
            
        elif geom_type == 'MultiPolygon':
            for i, polygon in enumerate(coordinates):
                coords = polygon[0]
                kml_coords = [(coord[0], coord[1]) for coord in coords]
                
                pol = kml.newpolygon(name=f"{location} Part {i+1}", description=description)
                pol.outerboundaryis = kml_coords
                pol.style.polystyle.color = color
                pol.style.polystyle.fill = 1
                pol.style.polystyle.outline = 1
                pol.style.linestyle.color = simplekml.Color.white
                pol.style.linestyle.width = 2
            
    # Generate KML string
    kml_string = kml.kml()
    return kml_string

def upload_to_gcs(file_content, filename, bucket_name):
    """Uploads file content to a specified Google Cloud Storage bucket."""
    try:
        # 1. Instantiate the GCS client
        # Instantiate client without credentials to use Application Default Credentials
        storage_client = storage.Client()
        
        # 2. Get the destination bucket and create the blob (file)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(filename)
        
        # 3. Upload the content
        # Set content type for KML files
        blob.upload_from_string(
            file_content, 
            content_type='application/vnd.google-earth.kml+xml'
        )
        
        print(f"✅ Successfully uploaded {filename} to gs://{bucket_name}/{filename}")
        
        # Return a simple dictionary indicating success.
        return {'action': 'uploaded'} 
        
    except Exception as e:
        print(f"❌ Error uploading to GCS bucket {bucket_name}: {e}")
        # Re-raise to ensure the main function fails if upload fails
        raise

def sync_kml_to_public_gcs():
    """Internal function to handle KML conversion and upload to the public GCS bucket."""
    
    # Update the print statement
    print(f"==== Starting GeoJSON to KML sync to gs://{PUBLIC_HOSTING_BUCKET} ====")
    
    # 1. Download GeoJSON from GCS
    print(f"Downloading GeoJSON from gs://{GCS_BUCKET_NAME}/{GEOJSON_PATH}")
    geojson_data = get_geojson_from_gcs()
    feature_count = len(geojson_data.get('features', []))
    print(f"Loaded {feature_count} features")
    
    # 2. Convert to KML
    print("Converting GeoJSON to KML...")
    kml_content = geojson_to_kml(geojson_data)
    print(f"KML generated, size: {len(kml_content)} bytes")
    
    # 3. Upload to GCS public bucket
    filename = KML_FILENAME
    
    # Call the upload function with the public bucket name
    gcs_result = upload_to_gcs(kml_content, filename, PUBLIC_HOSTING_BUCKET)
    
    print(f"==== Sync complete: {gcs_result['action']} ====")
    
    # Simplify the return dictionary
    return {
        'success': True,
        'action': gcs_result['action'],
        'message': f"Successfully {gcs_result['action']} KML file to public GCS bucket",
        'feature_count': feature_count,
        'filename': filename
    }


# ======================================================================
# --- MAIN WORKFLOW FUNCTIONS ---
# ======================================================================

@functions_framework.http
def check_for_changes(request):
    """
    Main Cloud Function entry point.
    1. Fetches wastewater data and checks for changes.
    2. If changes exist, recalculates and updates the GeoJSON in GCS.
    3. Calls the KML sync process to the public GCS bucket.
    """
    print("Function started: check_for_changes.")
    
    # --- Part 1: Fetch and Check Hash ---
    try:
        response = requests.get(WASTEWATER_API_URL, timeout=30)
        response.raise_for_status()
        wastewater_data = response.json()
        current_data_string = json.dumps(wastewater_data, sort_keys=True)
        current_hash = hashlib.sha256(current_data_string.encode('utf-8')).hexdigest()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch data from API: {e}")
        return ("Failed to fetch data.", 500)
        
    try:
        hash_blob = get_gcs_blob(GCS_BUCKET_NAME, LAST_HASH_FILE_PATH)
        if hash_blob.exists():
            last_hash = hash_blob.download_as_text()
            if current_hash == last_hash:
                print("No changes detected in wastewater data. Checking KML sync...")
                # Even if no changes, we call the sync to ensure the KML file exists and is up-to-date
                try:
                    gcs_result = sync_kml_to_public_gcs()
                    return (f"No data changes. KML GCS sync: {gcs_result['action']}.", 200)
                except Exception as e:
                    return (f"No data changes. KML GCS sync failed: {str(e)}", 500)
        else:
            print("No previous hash found. Proceeding with analysis.")
    except Exception as e:
        print(f"Error checking last hash: {e}. Proceeding with analysis.")
        
    # --- Part 2: Load, Calculate, and Save GeoJSON ---
    
    perifereies_geometries = load_perifereies_data(GCS_BUCKET_NAME, PERIFEREIES_GEOJSON_PATH)
    if perifereies_geometries is None:
        return ("Failed to load perifereies data.", 500)
        
    new_zones_features = calculate_new_zones(perifereies_geometries, wastewater_data)
    
    if not new_zones_features:
        print("Analysis resulted in no new zones to save. Updating hash to prevent immediate re-run.")
        hash_blob = get_gcs_blob(GCS_BUCKET_NAME, LAST_HASH_FILE_PATH)
        hash_blob.upload_from_string(current_hash)
        return ("Analysis complete. No zones saved.", 200)
        
    try:
        # Construct the final FeatureCollection
        new_zones_geojson = {
            "type": "FeatureCollection",
            "features": new_zones_features
        }
        
        # Save GeoJSON
        output_blob = get_gcs_blob(GCS_BUCKET_NAME, OUTPUT_GEOJSON_PATH)
        output_blob.upload_from_string(
            json.dumps(new_zones_geojson),
            content_type="application/geo+json"
        )
        print(f"Saved new GeoJSON to GCS: gs://{GCS_BUCKET_NAME}/{OUTPUT_GEOJSON_PATH}")
        
        # Update hash
        hash_blob = get_gcs_blob(GCS_BUCKET_NAME, LAST_HASH_FILE_PATH)
        hash_blob.upload_from_string(current_hash)
        print("Hash file updated.")
        
    except Exception as e:
        print(f"Failed to save results to GCS: {e}")
        return ("Failed to save GeoJSON results.", 500)
        
    # --- Part 3: KML Conversion and GCS Upload ---
    try:
        gcs_result = sync_kml_to_public_gcs()
        
        return (f"Analysis complete. New GeoJSON saved. KML GCS sync: {gcs_result['action']}.", 200)
        
    except Exception as e:
        print(f"KML Sync to GCS Failed: {e}")
        # We return 200 here because the GeoJSON update (the primary goal) succeeded.
        return (f"Analysis complete. GeoJSON saved. KML sync failed: {str(e)}", 200)