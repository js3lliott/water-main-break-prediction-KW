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

data = load_data().to_json()

# Plot 1: Map of water main break locations
st.markdown("## Map of Water Main Breaks")

# # adding a slider to select the number of data points to be displayed on the map
# nrows = st.slider("Number of data points", 0, 3000, 100)

# # adding a dropdown menu to select the year of the data to be displayed on the map sorted by year
# year = st.selectbox("Year", sorted(data['year'].unique()))

# # adding a dropdown menu to select the type of asset to be displayed on the map
# asset = st.selectbox("Asset", data['asset_material'].unique())

# # adding a dropdown menu to select the age of the asset to be displayed on the map
# age = st.selectbox("Age", sorted(data['age'].unique()))

# # adding a dropdown menu to select the number of breaks per asset to be displayed on the map
# num_breaks = st.selectbox("Number of Breaks", sorted(data['num_breaks'].unique()))

# # adding a dropdown menu to select the size of the asset to be displayed on the map
# size = st.selectbox("Size", sorted(data['asset_size'].unique()))


# # filtering the data based on the user's selections
# data = data[data['year'] == year]
# # data = data[data['year'].dt.year == year]
# data = data[data['asset_material'] == asset]
# data = data[data['age'] == age]
# data = data[data['num_breaks'] == num_breaks]
# data = data[data['asset_size'] == size]

# # create a heatmap of the data
# st.pydeck_chart(pdk.Deck(
#     map_style='mapbox://styles/mapbox/light-v9',
#     initial_view_state=pdk.ViewState(
#         latitude=43.4500,
#         longitude=-80.5000,
#         zoom=10,
#         pitch=50,
#     ),
#     layers=[
#         pdk.Layer(
#             'HeatmapLayer',
#             data=data,
#             get_position='[longitude, latitude]',
#             get_weight='[num_breaks]',
#             radius=200,
#             threshold=0.05,
#             aggregation='MEAN',
#             pickable=True,
#             extruded=True,
#         ),
#     ],
# ))

# create a map of the filtered data
st.write(pdk.Deck(
    map_style='mapbox://styles/mapbox/light-v9',
    initial_view_state=pdk.ViewState(
            latitude=43.4500,
            longitude=-80.5000,
            zoom=10,
            pitch=50,
        ),
    layers=[
        pdk.Layer(
            'ScatterplotLayer',
            data=data,
            get_position=['longitude', 'latitude'],
            get_color='[200, 30, 0, 160]',
            get_radius=200,
        ),
    ],
))

# # Plot 2: Heatmap of water main break locations
# st.markdown("## Heatmap of Water Main Breaks")

# # creating a heatmap of the filtered data
# st.pydeck_chart(pdk.Deck(
#     map_style='mapbox://styles/mapbox/light-v9',
#     initial_view_state=pdk.ViewState(
#         latitude=43.4500,
#         longitude=-80.5000,
#         zoom=10,
#         pitch=50,
#     ),
#     layers=[
#         pdk.Layer(
#             'HeatmapLayer',
#             data=data,
#             get_position='[longitude, latitude]',
#             get_weight='[num_breaks]',
#             radius=200,
#             threshold=0.05,
#             aggregation='MEAN',
#             pickable=True,
#             extruded=True,
#         ),
#     ],
# ))