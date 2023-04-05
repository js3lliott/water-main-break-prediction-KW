import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import plotly.express as px

# st.set_page_config(layout="wide")

DATA_PATH = ("data/processed/cleaned_break_data.csv")

st.title("Water Main Breaks in Kitchener-Waterloo")

@st.cache(persist=True) # this prevents having to load the data every time there is a change in the dataset

def load_data():
    data = pd.read_csv(DATA_PATH, parse_dates=['INCIDENT_DATE'])
    data.dropna(subset=['LATITUDE', 'LONGITUDE', 'ASSET_EXISTS'], inplace=True)
    data = data[data['ASSET_EXISTS'] != 'N']
    data['INCIDENT_DATE'] = pd.to_datetime(data['INCIDENT_DATE'], format='%Y-%m-%d').dt.date
    
    data['year'] = pd.DatetimeIndex(data['INCIDENT_DATE']).year
    lowercase = lambda x: str(x).lower()
    data.rename(lowercase, axis='columns', inplace=True)
    
    num_breaks = {}
    for pipe in data['assetid']:
        if pipe in num_breaks:
            num_breaks[pipe] += 1
        else:
            num_breaks[pipe] = 1
    data['num_breaks'] = data['assetid'].map(num_breaks)
    
    data['age'] = (np.floor((pd.to_datetime(data['incident_date']) - 
                        pd.to_datetime(data['asset_year_installed'])).dt.days / 365.25)).astype(int)
    return data


data = load_data()
# load in the test data
test_prediction_data = pd.read_csv("data/processed/test_predict_data.csv")

# create a sidebar menu and put each of the below charts on a new page
st.sidebar.title("Menu")

page = st.sidebar.radio("Go to", ["Home", "Scatterplot", "Heatmap", "Break Predictions", "Predictions by Age", "Predictions by Hexagon Layer"])

if page == "Home":
    st.write("""The data was collected by the City of Kitchener and is available on [Kitchener's Open Data Portal](https://data.kitchener.ca/dataset/water-main-breaks).""")
    st.write(
    """
    Water is one of our most precious resources, and the infrastructure that delivers it is often taken for granted. 
    But what happens when that infrastructure fails? In Kitchener-Waterloo, Canada, the city is collecting data on 
    water main breaks to better understand and prevent them. And now, we've taken that data and built a machine learning model 
    that predicts where and when water main breaks are most likely to occur. With this model, we can proactively address potential 
    issues and prevent costly and disruptive water main breaks before they happen. Are you ready to dive in and explore the exciting 
    world of predictive analytics for water infrastructure? Let's get started.

    When you're ready to explore the data, use the menu on the left to navigate to the different pages.
    """
)
    # st.write(data)
    # insert the break_map image
    st.image("images/break_map.png", use_column_width=True)

elif page == "Scatterplot":
    st.header("Scatterplot of Water Main Breaks")
    st.write("This scatterplot shows the location of water main breaks in Kitchener-Waterloo. Each location is a unique water main break incident.")
    # show the scatterplot but with smaller points
    st.plotly_chart(px.scatter_mapbox(data, lat='latitude', lon='longitude', zoom=10, mapbox_style="carto-positron"))
elif page == "Heatmap":
    st.header("Heatmap of Water Main Breaks")
    st.write("This heatmap shows the location of water main breaks in Kitchener-Waterloo. The darker the colour, the more breaks at that location.")
    st.plotly_chart(px.density_mapbox(data, lat='latitude', lon='longitude', z='num_breaks', radius=10,
                                    center=dict(lat=43.4643, lon=-80.5204), zoom=10, mapbox_style="carto-positron"))
elif page == "Break Predictions":
    st.header("Predicted Water Main Breaks")
    st.write("This heatmap shows the predicted location of water main breaks in Kitchener-Waterloo. The darker the colour, the more breaks at that location.")
    st.plotly_chart(px.density_mapbox(test_prediction_data, lat='latitude', lon='longitude', z='predictions', radius=10,
                                    center=dict(lat=43.4643, lon=-80.5204), zoom=10, mapbox_style="carto-positron"))
elif page == "Predictions by Age":
    st.header("Predicted Water Main Breaks by Age")
    st.write("This heatmap shows the predicted location of water main breaks in Kitchener-Waterloo. The darker the colour, the more breaks at that location. The animation shows the predicted breaks by age of the pipe.")
    st.plotly_chart(px.density_mapbox(test_prediction_data, lat='latitude', lon='longitude', z='predictions', radius=10,
                                    center=dict(lat=43.4643, lon=-80.5204), zoom=10, mapbox_style="carto-positron", animation_frame=test_prediction_data['age_at_break'].sort_values(ascending=True)))
elif page == "Predictions by Hexagon Layer":
    st.header("Predicted Water Main Breaks by Hexagon Layer")
    st.write("This heatmap is a fun visual that shows the pipe breaks as a hexagonal point. The darker and higher the hexagon, the more breaks occurred at that location")
    st.pydeck_chart(pdk.Deck(
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
                data=test_prediction_data,
                get_position='[longitude, latitude]',
                radius=150,
                elevation_scale=4,
                elevation_range=[0, 1000],
                pickable=True,
                extruded=True,
            ),
        ],
    ))
