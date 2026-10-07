"""คำนวณตัวชี้วัดความคลาดเคลื่อนสำหรับผลพยากรณ์เทียบค่าจริง พร้อม baseline comparisons (Naïve & Seasonal Naïve)."""
import logging
from typing import Optional, Dict, Any
import numpy as np

logger = logging.getLogger("forecast_model.metrics")


def calculate_mae(y_true, y_pred) -> Optional[float]:
    """คำนวณค่าเฉลี่ยของค่าสัมบูรณ์ความคลาดเคลื่อน (MAE). คืน None ถ้าไม่มีข้อมูลหรือขนาดไม่เท่ากัน."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if len(y_true) == 0 or len(y_pred) == 0 or len(y_true) != len(y_pred):
        return None
    return float(np.mean(np.abs(y_true - y_pred)))


def calculate_rmse(y_true, y_pred) -> Optional[float]:
    """คำนวณรากที่สองของค่าเฉลี่ยกำลังสองของความคลาดเคลื่อน (RMSE). คืน None ถ้าไม่มีข้อมูลหรือขนาดไม่เท่ากัน."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if len(y_true) == 0 or len(y_pred) == 0 or len(y_true) != len(y_pred):
        return None
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def calculate_mape(y_true, y_pred) -> Optional[float]:
    """คำนวณ MAPE เป็นเปอร์เซ็นต์ โดยละรายการที่ค่าจริงเป็นศูนย์.
    
    ข้อจำกัดของ MAPE (Limitations):
    - เมื่อค่าจริงเป็นศูนย์ (y_true == 0) จะเกิดการหารด้วยศูนย์ (Division by Zero)
    - เมื่อค่าจริงมีค่าน้อยมากใกล้ศูนย์ ค่า MAPE จะบวมสูงผิดปกติ (Severe Distortion)
    - หากค่าจริงทุกจุดเป็นศูนย์ หรือขนาดไม่เท่ากัน จะคืน None (ไม่มีผลประเมิน) แทนการคืน 0.0
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if len(y_true) == 0 or len(y_pred) == 0 or len(y_true) != len(y_pred):
        return None

    non_zero = (y_true != 0) & (~np.isnan(y_true))
    if not np.any(non_zero):
        logger.warning("All actual values are zero; MAPE is undefined (returning None)")
        return None

    return float(np.mean(np.abs((y_true[non_zero] - y_pred[non_zero]) / y_true[non_zero])) * 100.0)


def calculate_naive_forecast(y_train: np.ndarray, steps: int) -> np.ndarray:
    """Naïve Baseline: ใช้ค่าจริงจุดล่าสุดของชุด train พยากรณ์ไปข้างหน้าทุก steps."""
    y_train = np.asarray(y_train, dtype=float)
    if len(y_train) == 0:
        raise ValueError("y_train cannot be empty for Naive baseline")
    last_val = y_train[-1]
    return np.full(steps, last_val)


def calculate_seasonal_naive_forecast(y_train: np.ndarray, steps: int, season_length: int = 12) -> np.ndarray:
    """Seasonal Naïve Baseline: ใช้ค่าจริงของฤดูกาลเดียวกันในปีก่อนหน้า (m=season_length).
    
    หากข้อมูล train สั้นกว่า season_length จะ fallback ไปใช้ Naïve baseline.
    """
    y_train = np.asarray(y_train, dtype=float)
    n = len(y_train)
    if n == 0:
        raise ValueError("y_train cannot be empty for Seasonal Naive baseline")
    if n < season_length:
        return calculate_naive_forecast(y_train, steps)

    preds = []
    for step in range(steps):
        idx = -season_length + (step % season_length)
        preds.append(y_train[idx])
    return np.array(preds)


def evaluate_forecast_against_baselines(
    y_train: np.ndarray,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    season_length: int = 12
) -> Dict[str, Any]:
    """ประเมินเปรียบเทียบผลพยากรณ์ของโมเดลกับ Naïve และ Seasonal Naïve Baselines."""
    y_train = np.asarray(y_train, dtype=float)
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    steps = len(y_true)

    # 1. Model metrics
    m_mae = calculate_mae(y_true, y_pred)
    m_rmse = calculate_rmse(y_true, y_pred)
    m_mape = calculate_mape(y_true, y_pred)

    # 2. Naive Baseline
    naive_pred = calculate_naive_forecast(y_train, steps)
    n_mae = calculate_mae(y_true, naive_pred)
    n_rmse = calculate_rmse(y_true, naive_pred)
    n_mape = calculate_mape(y_true, naive_pred)

    # 3. Seasonal Naive Baseline
    snaive_pred = calculate_seasonal_naive_forecast(y_train, steps, season_length=season_length)
    sn_mae = calculate_mae(y_true, snaive_pred)
    sn_rmse = calculate_rmse(y_true, snaive_pred)
    sn_mape = calculate_mape(y_true, snaive_pred)

    has_zeros = bool(np.any(y_true == 0))

    return {
        "eval_status": "evaluated" if m_mae is not None else "not_evaluatable",
        "mae": m_mae,
        "rmse": m_rmse,
        "mape": m_mape,
        "baselines": {
            "naive": {
                "name": "Naïve (Persistence)",
                "mae": n_mae,
                "rmse": n_rmse,
                "mape": n_mape,
            },
            "seasonal_naive": {
                "name": f"Seasonal Naïve (m={season_length})",
                "mae": sn_mae,
                "rmse": sn_rmse,
                "mape": sn_mape,
            }
        },
        "evaluation_notes": {
            "mape_limitation": (
                "MAPE is sensitive to near-zero actual values and undefined when actual is zero. "
                "MAE and RMSE provide more robust evaluation for inventory series."
            ),
            "zero_actuals_present": has_zeros,
        }
    }
