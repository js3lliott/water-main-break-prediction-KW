import pandas as pd
import numpy as np
import src

# import the data and features from the src folder
<<<<<<< HEAD
from src.data.extract_data import extract_data
=======
<<<<<<< HEAD
from src.data.fetch_data import fetch_data
=======
from src.data.extract_data import extract_data
>>>>>>> 4649fdb0e1726d876555435d5b0a4ea8f52c024e
>>>>>>> 51214857bcc071c461d59c12700ae1b6cd216ef7
from src.features.process_data import process_data

# from data import extract_data
# from features import process_data

import sklearn
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import make_pipeline

import mlflow
import mlflow.sklearn

# Collect the data
# data = extract_data()

# Process the data
data = process_data()

# Grabbing the model data that was just processed
data = pd.read_csv('data/processed/model_data.csv')

# Split the data
X = data.drop('failure_rate', axis=1)
y = data['failure_rate']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Define the hyperparameters
n_estimators = [10, 50, 100, 150]
max_depth = [1, 3, 5, 7]
min_samples_split = [2, 5, 10, 15]
min_samples_leaf = [1, 2, 4, 6]

def train_rf(X_train, X_test, y_train, y_test, n_estimators, max_depth, min_samples_split, min_samples_leaf):
    with mlflow.start_run():

        # Create the model
        rf = RandomForestRegressor(n_estimators=n_estimators, max_depth=max_depth, min_samples_split=min_samples_split, min_samples_leaf=min_samples_leaf)

        # Create the pipeline
        pipeline = make_pipeline(StandardScaler(), rf)

        # Fit the model
        pipeline.fit(X_train, y_train)

        # Evaluate the model
        # y_pred = pipeline.predict(X_test)

        # Calculate the accuracy
        score = pipeline.score(X_test, y_test)

        # Log the parameters
        mlflow.log_param("n_estimators", rf.n_estimators)
        mlflow.log_param("max_depth", rf.max_depth)
        mlflow.log_param("min_samples_split", rf.min_samples_split)
        mlflow.log_param("min_samples_leaf", rf.min_samples_leaf)

        # Log the score
        mlflow.log_metric("score", score)

        # Log the model
        mlflow.sklearn.log_model(pipeline, "rf-model")

        # print the results
        print(f"n_estimators: {rf.n_estimators}")
        print(f"max_depth: {rf.max_depth}")
        print(f"min_samples_split: {rf.min_samples_split}")
        print(f"min_samples_leaf: {rf.min_samples_leaf}")
        print(f"score: {score}")

# call the function for each combination of hyperparameters
for n in n_estimators:
    for d in max_depth:
        for s in min_samples_split:
            for l in min_samples_leaf:
                train_rf(X_train, X_test, y_train, y_test, n, d, s, l)

