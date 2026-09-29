import pandas as pd
import numpy as np

class PreprocessingError(Exception):
    pass

def prepare_time_series(df: pd.DataFrame, target_col: str, date_col: str) -> pd.DataFrame:
    """
    1. Validate Frequency (Monthly)
    2. Handle Missing values
    3. Handle NaN and Infinite values
    """
    if df.empty:
        raise PreprocessingError("Insufficient data: Dataset is empty.")
        
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    
    # Check for invalid values
    if df[target_col].isin([np.inf, -np.inf]).any():
        df[target_col] = df[target_col].replace([np.inf, -np.inf], np.nan)
        
    df = df.dropna(subset=[target_col])
    
    if len(df) < 2:
        raise PreprocessingError("Insufficient data: Need at least 2 data points after dropping NaNs.")
    
    # Set index and aggregate by month (Month Start)
    df.set_index(date_col, inplace=True)
    
    # Resample to Monthly frequency and sum target column
    # If exogenous variables are added later, aggregation logic should change per column
    agg_dict = {target_col: 'sum'}
    # Support exogenous variables if present
    exog_cols = [c for c in df.columns if c != target_col]
    for c in exog_cols:
        agg_dict[c] = 'mean'
        
    monthly_df = df.resample('MS').agg(agg_dict)
    
    # Handle missing months by forward fill then backward fill, or 0 for target
    monthly_df[target_col] = monthly_df[target_col].fillna(0.0)
    for c in exog_cols:
        monthly_df[c] = monthly_df[c].ffill().bfill().fillna(0.0)
        
    if len(monthly_df) < 12:
        # Require at least 12 months for a minimal reliable seasonal/annual check, but let's just say 6
        raise PreprocessingError("Insufficient data: Need at least 12 months of data for reliable forecasting.")
        
    return monthly_df

def chronological_split(df: pd.DataFrame, train_ratio: float = 0.8):
    """
    Chronological Train/Test split.
    """
    if len(df) < 2:
        raise PreprocessingError("Not enough data to split.")
        
    n_train = int(len(df) * train_ratio)
    
    if n_train == 0 or n_train == len(df):
        raise PreprocessingError("Split ratio leaves train or test empty.")
        
    train_df = df.iloc[:n_train]
    test_df = df.iloc[n_train:]
    
    return train_df, test_df
