import requests
import pandas as pd
import schedule
import time
import sqlite3
import datetime

def extract_data():
    """Extract data from the ArcGIS API."""

    url = 'https://services1.arcgis.com/qAo1OsXi67t7XgmS/arcgis/rest/services/Water_Main_Breaks/FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson'
    response =  requests.get(url)
    data = response.json()

    # converting the GeoJSON file to a dataframe and then applying the pandas series method to extract the features from 'properties' key
    df = pd.DataFrame(data['features'])
    df = df['properties'].apply(pd.Series)
    # saving the dataframe to a csv file with the date it was extracted
    df.to_csv(f'data/raw/break_data_{datetime.datetime.now().strftime("%Y-%m-%d")}.csv', index=False)
    

    # saving the dataframe to a sqlite database and replacing the older data
    conn = sqlite3.connect('data/raw/break_data.db')
    df.to_sql('break_data', conn, if_exists='replace', index=False)
    conn.close()

    return df


extract_data()

# schedule.every().sunday.at("09:00").do(extract_data)

# while True:
#     schedule.run_pending()
#     time.sleep(1)