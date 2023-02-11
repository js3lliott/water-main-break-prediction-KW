import pandas as pd
import numpy as np

from src.data.extract_data import extract_data
from src.features.process_data import process_data

import sklearn
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import make_pipeline


# Collect the data
data = extract_data()

# Process the data
data = process_data(data)

# Split the data
X = data.drop(['num_breaks'], axis=1)