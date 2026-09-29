import numpy as np

def calculate_mae(y_true, y_pred) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))

def calculate_rmse(y_true, y_pred) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred)**2)))

def calculate_mape(y_true, y_pred) -> float:
    # avoid division by zero
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    non_zero = y_true != 0
    if not np.any(non_zero):
        return 0.0
    return float(np.mean(np.abs((y_true[non_zero] - y_pred[non_zero]) / y_true[non_zero])) * 100)
