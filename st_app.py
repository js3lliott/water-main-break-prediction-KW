import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import plotly.express as px

# st.set_page_config(layout="wide")

DATA_PATH = ("data/processed/cleaned_break_data.csv")

st.title("Water Main Breaks in Kitchener-Waterloo")
st.markdown("This map shows the location of water main breaks in Kitchener-Waterloo. The data was collected by the City of Kitchener and is available on [Kitchener's Open Data Portal](https://data.kitchener.ca/dataset/water-main-breaks).")

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

# create a dropdown menu to select the graph to display
st.selectbox("Select a graph", ["Scatterplot", "Heatmap"])


st.markdown("## Scatterplot of Water Main Breaks")
# have each of the points labeled with their attributes

st.map(data)


st.markdown("## Heatmap of Water Main Breaks")
st.plotly_chart(px.density_mapbox(data, lat='latitude', lon='longitude', z='num_breaks', radius=10,
                                    center=dict(lat=43.4643, lon=-80.5204), zoom=10, mapbox_style="carto-positron"))


# load in the model data
# model_data = pd.read_csv("data/processed/model_data.csv")

# load in the predictions from the baseline model notebook
# predictions = pd.read_csv("data/processed/predictions.csv")

# load in the final data
# final_data = pd.read_csv("data/processed/final_data.csv")

# # drop the rows with infinite failure rates
# inf_values = final_data[final_data['failure_rate'] == np.inf]
# final_data = final_data.drop(inf_values.index, axis=0)

# final_data.drop(['incident_date', 'asset_year_installed'], axis=1, inplace=True)

# final_X = final_data.drop('failure_rate', axis=1)
# final_y = final_data['failure_rate']

# X_train, X_test, y_train, y_test = train_test_split(final_X, final_y, test_size=0.2, random_state=42)
# rf = RandomForestRegressor()
# rf.fit(X_train, y_train)

# y_pred = rf.predict(X_test)

# lat = X_test['latitude'].values
# lon = X_test['longitude'].values
# break_locations = list(zip(lat, lon))

# load in the test data
test_prediction_data = pd.read_csv("data/processed/test_predict_data.csv")


st.markdown("## Predicted Water Main Breaks")
st.plotly_chart(px.density_mapbox(test_prediction_data, lat='latitude', lon='longitude', z='predictions', radius=10,
                                    center=dict(lat=43.4643, lon=-80.5204), zoom=10, mapbox_style="carto-positron"))

st.markdown("## Predicted Water Main Breaks by Age")
st.plotly_chart(px.density_mapbox(test_prediction_data, lat='latitude', lon='longitude', z='predictions', radius=10,
                                    center=dict(lat=43.4643, lon=-80.5204), zoom=10, mapbox_style="carto-positron", animation_frame=test_prediction_data['age_at_break'].sort_values(ascending=True)))


# create a hexagon layer map for the predicted water main breaks and make things translucent
st.markdown("## Predicted Water Main Breaks")
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
