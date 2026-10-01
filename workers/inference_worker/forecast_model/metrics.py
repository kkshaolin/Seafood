"""คำนวณตัวชี้วัดความคลาดเคลื่อนสำหรับผลพยากรณ์เทียบค่าจริง"""
import numpy as np

def calculate_mae(y_true, y_pred) -> float:
    """คำนวณค่าเฉลี่ยของค่าสัมบูรณ์ความคลาดเคลื่อน (MAE)"""
    return float(np.mean(np.abs(y_true - y_pred)))

def calculate_rmse(y_true, y_pred) -> float:
    """คำนวณรากที่สองของค่าเฉลี่ยกำลังสองของความคลาดเคลื่อน (RMSE)"""
    return float(np.sqrt(np.mean((y_true - y_pred)**2)))

def calculate_mape(y_true, y_pred) -> float:
    """คำนวณ MAPE เป็นเปอร์เซ็นต์ โดยละรายการที่ค่าจริงเป็นศูนย์"""
    # avoid division by zero
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    non_zero = y_true != 0
    if not np.any(non_zero):
        return 0.0
    return float(np.mean(np.abs((y_true[non_zero] - y_pred[non_zero]) / y_true[non_zero])) * 100)
