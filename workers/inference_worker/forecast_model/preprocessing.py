"""ตรวจสอบและเตรียมข้อมูลอนุกรมเวลาก่อนนำไปฝึกหรือประเมินโมเดล"""
import pandas as pd
import numpy as np

class PreprocessingError(Exception):
    """ข้อผิดพลาดเมื่อข้อมูลไม่เพียงพอหรือไม่พร้อมสำหรับการพยากรณ์"""
    pass

def prepare_time_series(df: pd.DataFrame, target_col: str, date_col: str) -> pd.DataFrame:
    """
    แปลงวันที่และทำความสะอาด target จากนั้นรวมข้อมูลเป็นรายเดือน

    target จะรวมด้วยผลบวก; คอลัมน์ตัวแปรภายนอกจะเฉลี่ยรายเดือน
    เดือนที่ขาดจะเติม target ด้วยศูนย์ และเติมตัวแปรภายนอกด้วยค่าก่อนหน้า/
    ค่าถัดไปก่อนใช้ศูนย์เป็นค่าเริ่มต้น ตรวจข้อมูลขั้นต่ำก่อนคืน DataFrame
    """
    if df.empty:
        raise PreprocessingError("Insufficient data: Dataset is empty.")
        
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    
    # ค่าอนันต์ใน target ถูกถือเป็น missing ก่อนทำความสะอาด
    if df[target_col].isin([np.inf, -np.inf]).any():
        df[target_col] = df[target_col].replace([np.inf, -np.inf], np.nan)
        
    df = df.dropna(subset=[target_col])
    
    if len(df) < 2:
        raise PreprocessingError("Insufficient data: Need at least 2 data points after dropping NaNs.")
    
    # ใช้วันเป็น index และจัดกลุ่มตามจุดเริ่มต้นของแต่ละเดือน
    df.set_index(date_col, inplace=True)
    
    # รวม target ด้วยผลบวก และกำหนดวิธีรวมแยกตามชนิดคอลัมน์
    agg_dict = {target_col: 'sum'}
    # ตัวแปรอื่นทั้งหมดถือเป็น exogenous และเฉลี่ยภายในเดือน
    exog_cols = [c for c in df.columns if c != target_col]
    for c in exog_cols:
        agg_dict[c] = 'mean'
        
    monthly_df = df.resample('MS').agg(agg_dict)
    
    # เติมเดือนที่ไม่มีแถว: target เป็นศูนย์ ส่วน exogenous ใช้ ffill/bfill แล้วจึงใช้ศูนย์
    monthly_df[target_col] = monthly_df[target_col].fillna(0.0)
    for c in exog_cols:
        monthly_df[c] = monthly_df[c].ffill().bfill().fillna(0.0)
        
    if len(monthly_df) < 2:
        raise PreprocessingError("Insufficient data: Need at least 2 months of data for basic forecasting.")
        
    return monthly_df

def chronological_split(df: pd.DataFrame, train_ratio: float = 0.8):
    """
    แบ่ง train/test ตามลำดับเวลาโดยไม่สลับแถว และตรวจไม่ให้ชุดใดว่าง
    """
    if len(df) < 2:
        raise PreprocessingError("Not enough data to split.")
        
    n_train = int(len(df) * train_ratio)
    
    if n_train == 0 or n_train == len(df):
        raise PreprocessingError("Split ratio leaves train or test empty.")
        
    train_df = df.iloc[:n_train]
    test_df = df.iloc[n_train:]
    
    return train_df, test_df
