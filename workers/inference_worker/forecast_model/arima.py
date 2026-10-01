"""ฟังก์ชันฝึกและสร้างค่าพยากรณ์ด้วย ARIMA จาก statsmodels"""
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
import warnings

def train_arima(train_df: pd.DataFrame, target_col: str, exog_cols: list, p: int, d: int, q: int):
    """
    ฝึกโมเดล ARIMA ตามลำดับ (p, d, q) จากคอลัมน์เป้าหมาย

    หากระบุ exogenous columns จะส่งตัวแปรเหล่านั้นเป็น exog; หากไม่ระบุ
    จะฝึก ARIMA จาก target เพียงชุดเดียว
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
    พยากรณ์จำนวน steps จากโมเดลที่ฝึกแล้ว และคืนค่ากลางกับช่วงความเชื่อมั่น 95%

    เมื่อโมเดลใช้ตัวแปรภายนอก ให้ส่งค่าของช่วงอนาคตผ่าน future_exog
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        forecast_result = fitted_model.get_forecast(steps=steps, exog=future_exog)
        
    forecast_values = forecast_result.predicted_mean
    conf_int = forecast_result.conf_int(alpha=0.05) # 95% CI
    
    return forecast_values, conf_int
