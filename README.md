<img src="./data/high-res-KW-water-infrastructure.png" width="800" height="300" class="center">


# Water Main Pipe Break/Failure Prediction 🚱 🚧

## Introduction to the Project

This is a self-curated project, that was born out of coming across open source data on local water main breaks and wondering how can a phenomenon like this be predicted, or if they     could be predicted at all!

Water main breaks are a costly endeavour for municipalities all over North America, and cause significant disruptions to daily life in the regions they occur in. In Kitchener-Waterloo, which is where this data is collected from, in 2014, experienced a year's worth of water main breaks in the first three months of the year, resulting in $1.6 million cost to repair.

The question I try to answer with this analysis is - can machine learning be used to predict the frequency of water main breaks and highlight the most at-risk regions?

**Disclaimer**: This project presents conclusions that are of my own opinion and do not represent true business recommendations to any person and/or organization.


## Table of Contents

- [About the Dataset](#about-the-dataset)
- [Notebook Navigation](#notebook-navigation)
- [My Approach to Solve this Problem](#my-approach-to-solve-this-problem)
- [Technical Approach in This Project](#technical-approach-in-this-project)
- [Limitations of Analysis](#limitations-of-analysis)
- [Data Cleaning](#data-cleaning)
- [Data Analysis](#data-analysis)
- [Key Takeaways](#key-takeaways)
- [Business Recommendation](#business-recommendation)
- [Next Step](#next-step)
- [References](#references)


## About the Dataset
- This dataset contains water main break information for the township of Kitchener-Waterloo from as far back as the early 1900'2 to present day
- There are 2,752 observations and 46 features, with each row being a distinct observation of a water main break
- You can find the data publicly available here: [[Water Main Breaks]](https://open-kitchenergis.opendata.arcgis.com/datasets/KitchenerGIS::water-main-breaks/about)

## Notebook Navigation
Navigate to any notebook you want! The first few are data processing and feature engineering notebooks, feel free to skip those if you'd like. The ones that contain the meat of the project are the EDA notebook and the modeling notebook.

- [Initial Pre-processing](https://nbviewer.org/github/js3lliott/water-main-break-prediction-KW/blob/main/nbs/01_initial_preprocessing.ipynb)
- [Feature Engineering](https://nbviewer.org/github/js3lliott/water-main-break-prediction-KW/blob/main/nbs/02_feature_eng_preprocessing.ipynb)
- [Exploratory Data Analysis](https://nbviewer.org/github/js3lliott/water-main-break-prediction-KW/blob/main/nbs/03_water_main_heatmap.ipynb)
- [Modeling](https://nbviewer.org/github/js3lliott/water-main-break-prediction-KW/blob/main/nbs/04_baseline_model.ipynb)


## General Approach
There are several questions we can try and answer by analyzing this data such as which type of material breaks the msot, does the weather affect the frequency of breaks, etc. Those aren't the main objectives of this study but they could be answered as a result of the origianl scope which is - **which section of pipes are at a high risk of breaking within the next couple of years?**

I will be focusing on the main quantitative goal of the project first and then will possibly investigate further the qualitative questions.


## Technical Approach
- Initial pre-processing
    - Packages: pandas, numpy, matplotlib
    - in this notebook, I try and look at each feature and determine how much it would actually contribute to meaningful predictions when it comes to modeling. 
    - fill in NaN and unknown values
    - end result is a dataset that I can use for visualization and analysis
    

- Feature cleaning & engineering
    - Packages: pandas, numpy, matplotlib
    - here I take the cleaned data from the previous notebook and continue to filter out unneccessary features
    - utillize categorical feature encoding
    - in the end we've got a dataset that can be used in some machine learning models

- Exploratory Data Analysis
    - Packages: pandas, numpy, matplotlib, seaborn, plotly
    - I take the unprocessed original data and just do a quick scatter mapbox visualization showing the location of each break, with the size being the number of breaks the pipe has experienced

- Modeling
    - Packages: pandas, matplotlib, scikit-learn
    - quick baseline models are implemented and feature importances are calculated and visualized
    - the first set of predictions are also visualized in a scatter mapbox (plotly) that display the predicted frequency of breaks for a test set of pipe segments


## Limitations of Analysis
- This data is only for the Kitchener-Waterloo region
    - other municipalities might have different data and data standards for their water distribution systems
- The original data only includes water mains that have broken at least once over the course of the collection period, not all water mains dsitributed in the city
    - this could influence the calculation of the failure rate and doesn't predict if a water main could break if it's never broken before


## Data Cleaning
The first two notebooks are dedicated to cleaning the data. The first notebook is a first pass cleaning attempt to cut down on most of the redundant and unneccessary features. The second notebook still involves getting rid of features, but more so is dedicated to data formatting, imputation and categorical encoding.
- we go from 52 features down to 16, and 2,752 observations to 2,042 after the notebooks


## Data Analysis
This section covers the overall approach that was taken after pre-processing the data, basically covering the whole EDA process.

So far there are only a few completed visuals. As I iterate over the project, more visualizations will be added.