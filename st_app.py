import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import plotly.express as px

# Load data
DATA_PATH = ("data/processed/cleaned_break_data.csv")

# adding title and subtitle of map webpage
st.title("Water Main Breaks in Kitchener-Waterloo")
st.markdown("This map shows the location of water main breaks in Kitchener-Waterloo. The data was collected by the City of Kitchener and is available on [Kitchener's Open Data Portal](https://data.kitchener.ca/dataset/water-main-breaks).")

@st.cache(persist=True) # this prevents having to load the data every time there is a change in the dataset

def load_data():
    data = pd.read_csv(DATA_PATH, parse_dates=['INCIDENT_DATE'])
    data.dropna(subset=['LATITUDE', 'LONGITUDE', 'ASSET_EXISTS'], inplace=True)
    data = data[data['ASSET_EXISTS'] != 'N']
    data['INCIDENT_DATE'] = pd.to_datetime(data['INCIDENT_DATE'], format='%Y-%m-%d').dt.date
    # create a separate column for year
    data['year'] = pd.DatetimeIndex(data['INCIDENT_DATE']).year
    lowercase = lambda x: str(x).lower()
    data.rename(lowercase, axis='columns', inplace=True)
    # calculating the number of breaks per year for each asset
    num_breaks = {}
    for pipe in data['assetid']:
        if pipe in num_breaks:
            num_breaks[pipe] += 1
        else:
            num_breaks[pipe] = 1
    data['num_breaks'] = data['assetid'].map(num_breaks)
    # calculating the age of each asset
    data['age'] = (np.floor((pd.to_datetime(data['incident_date']) - 
                        pd.to_datetime(data['asset_year_installed'])).dt.days / 365.25)).astype(int)
    return data


data = load_data()

# create a scatterplot of the data points using streamlit map
# show the number of breaks for each asset when you hover over the point
st.markdown("## Scatterplot of Water Main Breaks")
st.map(data)

# create a heatmap of the data points using plotly express and streamlit and don't show the terrain
st.markdown("## Heatmap of Water Main Breaks")
st.plotly_chart(px.density_mapbox(data, lat='latitude', lon='longitude', z='num_breaks', radius=10,
                                    center=dict(lat=43.4643, lon=-80.5204), zoom=10, mapbox_style="carto-positron"))

# create a 3d map of the data points using pydeck
st.markdown("## 3D Map of Water Main Breaks")
st.write(
    pdk.Deck(
        map_style='mapbox://styles/mapbox/light-v9',
        initial_view_state=pdk.ViewState(
            latitude=43.4643,
            longitude=-80.5204,
            zoom=10,
            pitch=50,
        ),
        layers=[
            pdk.Layer(
                'HexagonLayer',
                data=data,
                get_position='[longitude, latitude]',
                get_color='[200, 30, 0, 160]',
                get_radius=100,
                elevation_scale=4,
                elevation_range=[0, 1000],
                pickable=True,
                extruded=True,
            ),
        ],
)
)



# # create a map of the data points using pydeck
# st.markdown("## Map of Water Main Breaks")
# st.pydeck_chart(pdk.Deck(
#     map_style='mapbox://styles/mapbox/light-v9',
#     initial_view_state=pdk.ViewState(
#         latitude=43.4643,
#         longitude=-80.5204,
#         zoom=10,
#         pitch=50,
#     ),
#     layers=[
#         pdk.Layer(
#             'ScatterplotLayer',
#             data=data,
#             get_position='[longitude, latitude]',
#             get_color='[200, 30, 0, 160]',
#             get_radius=100,
#         ),
#     ],
# ))
