import requests
import pandas as pd
import schedule
import time

def extract_data():
    """Extract data from the ArcGIS API."""

    url = 'https://services1.arcgis.com/qAo1OsXi67t7XgmS/arcgis/rest/services/Water_Main_Breaks/FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson'
    response =  requests.get(url)
    data = response.json()

    # converting the GeoJSON file to a dataframe and then applying the pandas series method to extract the features from 'properties' key
    df = pd.DataFrame(data['features'])
    df = df['properties'].apply(pd.Series)

    return df

schedule.every().sunday.at("09:00").do(extract_data)

while True:
    schedule.run_pending()
    time.sleep(1)