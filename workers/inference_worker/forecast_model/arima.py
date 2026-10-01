import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
import warnings

def train_arima(train_df: pd.DataFrame, target_col: str, exog_cols: list, p: int, d: int, q: int):
    """
    Train ARIMA model using statsmodels.
    If exog_cols is empty, it falls back to ARIMA.
    """
    y = train_df[target_col]
    exog = train_df[exog_cols] if exog_cols else None
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ARIMA(y, exog=exog, order=(p, d, q))
        fitted_model = model.fit()
        
    return fitted_model

def forecast_arima(fitted_model, steps: int, future_exog: pd.DataFrame = None):
    """
    Forecast using the fitted ARIMA model.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        forecast_result = fitted_model.get_forecast(steps=steps, exog=future_exog)
        
    forecast_values = forecast_result.predicted_mean
    conf_int = forecast_result.conf_int(alpha=0.05) # 95% CI
    
    return forecast_values, conf_int
