import pandas as pd
import numpy as np
import os
import src

from src.data.fetch_data import fetch_data


# Load the data
df = pd.read_csv('../data/raw/Nov_10_22_Water_Main_Breaks.csv')

# colummns to keep
df = df[['LONGITUDE', 'LATITUDE', 'OBJECTID', 'WATBREAKINCIDENTID', 'INCIDENT_DATE',
        'BREAK_TYPE', 'BREAK_NATURE', 'BREAK_APPARENT_CAUSE', 'POSITIVE_PRESSURE_MAINTANED', 
        'AIR_GAP_MAINTANED', 'MECHANICAL_REMOVAL', 'FLUSHING_EXCAVATION', 'HIGHER_VELOCITY_FLUSHING', 
        'ANODE_INSTALLED', 'BREAK_CATEGORIZATION', 'ROADSEGMENTID', 'STREET', 'ASSETID', 
        'ASSET_SIZE', 'ASSET_YEAR_INSTALLED', 'ASSET_MATERIAL', 'ASSET_EXISTS']]

# lowercase the cols
df.columns = df.columns.str.lower()

# convert INCIDENT_DATE to datetime
df['INCIDENT_DATE'] = pd.to_datetime(df['INCIDENT_DATE']).dt.date
df['ASSET_YEAR_INSTALLED'] = pd.to_datetime(df['ASSET_YEAR_INSTALLED'], format='%Y')


def fill_nulls(df, cols, value):
    """Fill null values of a specified column with a specified value."""
    df[cols] = df[cols].fillna(value, inplace=True)
    return df

# fill nulls
df_copy = df.copy()
df_copy = fill_nulls(df_copy, ['BREAK_APPARENT_CAUSE', 'BREAK_NATURE', 'BREAK_CATEGORIZATION', 'STREET'], 'UNKNOWN')
df_copy = fill_nulls(df_copy, 'ASSET_SIZE', df_copy['ASSET_SIZE'].mode()[0])


def replace_values(df, col, original_value, new_value):
    """Replace a value in a column with a specified value."""
    df[col] = df[col].replace(original_value, new_value)
    return df

df_copy = replace_values(df_copy, 'BREAK_NATURE', 'OTHER', 'UNKNOWN')
df_copy = replace_values(df_copy, 'BREAK_NATURE', 'OTHER: WATER SERVICE', 'WATER SERVICE')

def num_breaks(df):
    """Calculate and return the number of breaks per year for each asset"""
    num_breaks = {}
    
    for pipe in df_copy['assetid']:
        if pipe in num_breaks:
            num_breaks[pipe] += 1
        else:
            num_breaks[pipe] = 1
    
    df_copy['num_breaks'] = df_copy['assertid'].map(num_breaks)
    return df

df_copy = num_breaks(df_copy)

def calc_age(df):
    """Calculate and return the age of each asset"""
    df_copy['age'] = (np.floor((pd.to_datetime(df_copy['incident_date']) - 
                        pd.to_datetime(df_copy['asset_year_installed'])).dt.days / 365.25)).astype(int)
    return df

df_copy = calc_age(df_copy)

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
    return df