import pandas as pd
import numpy as np
import os
import src

<<<<<<< HEAD
from src.data.fetch_data import fetch_data
=======
from src.data.extract_data import extract_data
>>>>>>> 4649fdb0e1726d876555435d5b0a4ea8f52c024e


# Load the latest extracted data from the extract_data.py script
df = extract_data()
# instead of loading in new data, I'm going to save it for newer predicitons and use old data to process for now
# df = pd.read_csv('data/raw/Nov_10_22_Water_Main_Breaks.csv')

# colummns to keep
df = df[['X', 'Y', 'INCIDENT_DATE',
        'BREAK_TYPE', 'BREAK_NATURE', 'BREAK_APPARENT_CAUSE', 'POSITIVE_PRESSURE_MAINTANED', 
        'AIR_GAP_MAINTANED', 'MECHANICAL_REMOVAL', 'FLUSHING_EXCAVATION', 'HIGHER_VELOCITY_FLUSHING', 
        'ANODE_INSTALLED', 'BREAK_CATEGORIZATION', 'STREET', 'ASSETID', 
        'ASSET_SIZE', 'ASSET_YEAR_INSTALLED', 'ASSET_MATERIAL', 'ASSET_EXISTS']]

# rename X and Y to longitude and latitude
df.rename(columns={'X': 'longitude', 'Y': 'latitude'}, inplace=True)


def fill_nulls(df, cols, value):
    """Fill null values of a specified column with a specified value."""
    df[cols] = df[cols].fillna(value)
    return df


def replace_values(df, col, original_value, new_value):
    """Replace a value in a column with a specified value."""
    df[col] = df[col].replace(original_value, new_value)
    return df


def num_breaks(df):
    """Calculate and return the number of breaks per year for each asset"""
    num_breaks = {}
    
    for pipe in df['assetid']:
        if pipe in num_breaks:
            num_breaks[pipe] += 1
        else:
            num_breaks[pipe] = 1
    
    df['num_breaks'] = df['assetid'].map(num_breaks)
    return df


def calc_age(df):
    """Calculate and return the age of each asset"""
    df['age_at_break'] = np.floor((pd.to_datetime(df['incident_date']) -
                        pd.to_datetime(df['asset_year_installed'])).dt.days / 365.25)
    # covering a few edge cases
    df['age_at_break'].fillna(0, inplace=True)
    df = df[~np.isinf(df['age_at_break'])]
    df['age_at_break'] = df['age_at_break'].astype(int)

    # df['age_at_break'] = (np.floor((pd.to_datetime(df['incident_date'])) - 
    #                     pd.to_datetime(df['asset_year_installed'])).dt.days / 365.25).astype(int)
    # using the code above, I was getting the follwon error:
    # TypeError: ufunc 'floor' not supported for the input types, and the inputs could not be safely coerced to any supported types according to the casting rule ''safe''
    return df


def process_cat_cols(df):
    binary_cols = ['positive_pressure_maintaned', 'air_gap_maintaned', 'mechanical_removal', 
                    'flushing_excavation', 'higher_velocity_flushing', 'anode_installed', 'asset_exists']
    
    df = pd.get_dummies(df, columns=binary_cols, drop_first=True)

    # fix the names of the columns modified
    df = df.rename(columns={'positive_pressure_maintaned_Y': 'positive_pressure_maintaned',
                            'air_gap_maintaned_Y': 'air_gap_maintaned',
                            'mechanical_removal_Y': 'mechanical_removal',
                            'flushing_excavation_Y': 'flushing_excavation',
                            'higher_velocity_flushing_Y': 'higher_velocity_flushing',
                            'anode_installed_Y': 'anode_installed',
                            'asset_exists_Y': 'asset_exists'})

    # group some of the names of break nature
    df['break_nature'] = df['break_nature'].replace(['CIRCUMFERENTIAL AND FITTING/JOINT'], 'CIRCUMFERENTIAL')
    df['break_nature'] = df['break_nature'].replace(['CORROSION AND CIRCUMFERENTIAL',
                                                            'CORROSION AND LONGITUDINAL',
                                                            'CORROSION AND FITTING/JOINT',
                                                            'CORROSION - ROBAR SADDLE CORRODED AT SEAM'], 'CORROSION')
    df['break_nature'] = df['break_nature'].replace(['FITTING/JOINT AND LONGITUDINAL'], 'FITTING/JOINT')

    df['break_apparent_cause'] = df['break_apparent_cause'].replace(['UNKNOWN'], 'OTHER')

    # convert the categorical columns to numeric
    for feature in df[['break_type', 'break_nature', 'break_apparent_cause', 'break_categorization', 'asset_material']]:
        df[feature] = df[feature].astype('category')
        df[feature] = df[feature].cat.codes

    return df


def calc_failure_rate(df):
    """Calculate the failure rate of each asset"""
    df['failure_rate'] = round(df['num_breaks'] / df['age_at_break'], 4)
    infinity_failure_rates = df[df['failure_rate']== np.inf]
    df.drop(infinity_failure_rates.index, axis=0, inplace=True)
    df['failure_rate'] = round(df['num_breaks'] / df['age_at_break'], 4)
    return df


def process_data(df):  # sourcery skip: inline-immediately-returned-variable
    """Process the data"""
    # lowercase the cols
    df.columns = df.columns.str.lower()

    # convert INCIDENT_DATE to datetime
    df['incident_date'] = pd.to_datetime(df['incident_date']).dt.date
    df['asset_year_installed'] = pd.to_datetime(df['asset_year_installed'], format='%Y')

    # fill nulls
    df = fill_nulls(df, ['break_apparent_cause', 'break_nature', 'break_categorization', 'street'], 'UNKNOWN')
    df = fill_nulls(df, 'asset_size', df['asset_size'].mode()[0])

    # replace values
    df = replace_values(df, 'break_nature', 'OTHER', 'UNKNOWN')
    df = replace_values(df, 'break_nature', 'OTHER: WATER SERVICE', 'WATER SERVICE')
    
    # calculate number of breaks per year for each asset
    df = num_breaks(df)
    
    # calculate age of each asset
    df = calc_age(df)

    # processing categorical columns
    df = process_cat_cols(df)

    # drop rows where asset_exists is 0
    df = df[df['asset_exists'] == 1]

    # calculate failure rate
    df = calc_failure_rate(df)

    return df

# save to csv for modeling
model_data = process_data(df)
model_data.drop(['longitude', 'latitude', 'incident_date', 'asset_year_installed', 'street', 'assetid'], axis=1, inplace=True)
model_data.to_csv('data/processed/model_data.csv', index=False)