"""ฟังก์ชันฝึกและสร้างค่าพยากรณ์ด้วย ARIMA จาก statsmodels พร้อมระบบคัดเลือกพารามิเตอร์อัตโนมัติด้วย ACF / PACF"""
from __future__ import annotations

import logging
import warnings
from typing import Optional, List, Tuple

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX, SARIMAXResults
from statsmodels.tsa.stattools import adfuller, acf, pacf

logger = logging.getLogger("forecast_model.sarimax")


def determine_differencing_order(series: pd.Series, max_d: int = 2) -> int:
    """หาค่า d ที่เหมาะสมเพื่อให้ข้อมูลนิ่ง (Stationary) โดยใช้ Augmented Dickey-Fuller (ADF) test."""
    y = series.dropna().astype(float)
    if len(y) < 8:
        return 1

    for d in range(max_d + 1):
        curr_y = y.copy()
        for _ in range(d):
            curr_y = curr_y.diff().dropna()
        if len(curr_y) < 8:
            return d
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                adf_res = adfuller(curr_y)
                p_value = float(adf_res[1])
                logger.debug("ADF test for d=%d: p-value=%.4f", d, p_value)
                if p_value <= 0.05:
                    return d
        except Exception as e:
            logger.debug("ADF test failed for d=%d: %s", d, e)
            continue

    return 1


def analyze_acf_pacf(
    series: pd.Series,
    d: int = 0,
    max_p: int = 3,
    max_q: int = 3,
) -> Tuple[int, int]:
    """วิเคราะห์ ACF และ PACF จากข้อมูลที่ผ่าน differencing เพื่อหาขอบเขตของ p และ q."""
    y = series.dropna().astype(float)
    for _ in range(d):
        y = y.diff().dropna()

    n_samples = len(y)
    if n_samples < 8:
        return 1, 1

    nlags = min(12, n_samples // 2 - 1)
    if nlags < 2:
        return 1, 1

    sig_p, sig_q = 1, 1
    try:
        threshold = 1.96 / np.sqrt(n_samples)  # 95% confidence bounds
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # PACF สำหรับ lag ของ AR (p)
            pacf_vals = pacf(y, nlags=nlags)
            p_lags = [i for i in range(1, min(len(pacf_vals), max_p + 1)) if abs(pacf_vals[i]) > threshold]
            sig_p = max(p_lags) if p_lags else 1

            # ACF สำหรับ lag ของ MA (q)
            acf_vals = acf(y, nlags=nlags)
            q_lags = [i for i in range(1, min(len(acf_vals), max_q + 1)) if abs(acf_vals[i]) > threshold]
            sig_q = max(q_lags) if q_lags else 1
            
            logger.info(
                "ACF/PACF analysis (d=%d): PACF significant lags=%s -> p=%d; ACF significant lags=%s -> q=%d",
                d, p_lags, sig_p, q_lags, sig_q
            )
    except Exception as e:
        logger.warning("ACF/PACF calculation failed: %s, fallback to (1, 1)", e)

    return sig_p, sig_q


def select_optimal_arima_order(
    train_df: pd.DataFrame,
    target_col: str,
    exog_cols: Optional[List[str]] = None,
    max_p: int = 3,
    max_q: int = 3,
    max_d: int = 2,
) -> Tuple[int, int, int]:
    """
    วิเคราะห์ความนิ่ง (ADF) เพื่อหา d, ตรวจสอบ ACF / PACF เพื่อหา significant lags
    และเปรียบเทียบ AIC เพื่อคัดเลือกชุดพารามิเตอร์ (p, d, q) ที่มีประสิทธิภาพสูงสุด
    """
    y = train_df[target_col].dropna().astype(float)
    exog = train_df[exog_cols] if exog_cols else None

    # 1. หาค่า d ด้วย ADF
    d = determine_differencing_order(y, max_d=max_d)

    # 2. วิเคราะห์ ACF/PACF เพื่อดูโครงสร้าง lag
    sig_p, sig_q = analyze_acf_pacf(y, d=d, max_p=max_p, max_q=max_q)

    # 3. กำหนด Candidates ในการทดสอบ AIC (ครอบคลุมค่าสำคัญและขอบเขตรอบข้าง)
    p_candidates = sorted(set([0, 1, 2, sig_p, min(sig_p + 1, max_p)]))
    q_candidates = sorted(set([0, 1, 2, sig_q, min(sig_q + 1, max_q)]))
    p_candidates = [p for p in p_candidates if p <= max_p]
    q_candidates = [q for q in q_candidates if q <= max_q]

    best_aic = float("inf")
    best_order = (sig_p, d, sig_q)

    for p in p_candidates:
        for q in q_candidates:
            if p == 0 and q == 0 and d == 0:
                continue
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    fitted = ARIMA(y, exog=exog, order=(p, d, q)).fit()
                    if fitted.aic < best_aic:
                        best_aic = fitted.aic
                        best_order = (p, d, q)
            except Exception:
                continue

    logger.info("Optimal ARIMA order selected: ARIMA%s with AIC=%.2f", best_order, best_aic)
    return best_order


def select_optimal_sarimax_order(
    train_df: pd.DataFrame,
    target_col: str,
    exog_cols: Optional[List[str]] = None,
    seasonal_period: int = 12,
    max_p: int = 2,
    max_q: int = 2,
    max_d: int = 2,
    max_P: int = 1,
    max_Q: int = 1,
    max_D: int = 1,
) -> Tuple[Tuple[int, int, int], Tuple[int, int, int, int]]:
    """
    ค้นหาพารามิเตอร์ SARIMAX (p,d,q)(P,D,Q,s) ที่เหมาะสมที่สุดโดยใช้ AIC
    """
    y = train_df[target_col].dropna().astype(float)
    exog = train_df[exog_cols] if exog_cols else None
    d = determine_differencing_order(y, max_d=max_d)
    sig_p, sig_q = analyze_acf_pacf(y, d=d, max_p=max_p, max_q=max_q)

    p_candidates = sorted(set([0, 1, sig_p]))
    q_candidates = sorted(set([0, 1, sig_q]))
    s = seasonal_period if len(y) >= (seasonal_period * 2) else 0

    best_aic = float("inf")
    best_order = (sig_p, d, sig_q)
    best_seasonal = (0, 0, 0, s)

    seasonal_candidates = [(0, 0, 0, s)]
    if s > 0:
        seasonal_candidates.extend([
            (1, 0, 0, s),
            (0, 1, 0, s),
            (1, 1, 0, s),
            (0, 1, 1, s),
            (1, 0, 1, s),
        ])

    for p in p_candidates:
        for q in q_candidates:
            if p == 0 and q == 0 and d == 0:
                continue
            for P, D, Q, s_period in seasonal_candidates:
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        mod = SARIMAX(
                            y,
                            exog=exog,
                            order=(p, d, q),
                            seasonal_order=(P, D, Q, s_period),
                            enforce_stationarity=False,
                            enforce_invertibility=False,
                        )
                        res = mod.fit(disp=False, maxiter=50)
                        if res.aic < best_aic:
                            best_aic = res.aic
                            best_order = (p, d, q)
                            best_seasonal = (P, D, Q, s_period)
                except Exception:
                    continue

    logger.info("Optimal SARIMAX order: %s x %s with AIC=%.2f", best_order, best_seasonal, best_aic)
    return best_order, best_seasonal


def train_sarimax(
    train_df: pd.DataFrame,
    target_col: str,
    exog_cols: Optional[List[str]] = None,
    p: int = 1,
    d: int = 1,
    q: int = 1,
    P: int = 0,
    D: int = 0,
    Q: int = 0,
    s: int = 0,
):
    """
    ฝึกโมเดล SARIMAX ตามลำดับ (p, d, q)(P, D, Q, s) พร้อมตัวแปรภายนอก exog_cols
    """
    y = train_df[target_col].astype(float)
    exog = train_df[exog_cols].astype(float) if exog_cols else None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = SARIMAX(
            y,
            exog=exog,
            order=(p, d, q),
            seasonal_order=(P, D, Q, s),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fitted_model = model.fit(disp=False, maxiter=100)

    return fitted_model


def forecast_sarimax(fitted_model, steps: int, future_exog: Optional[pd.DataFrame] = None):
    """
    พยากรณ์จำนวน steps จากโมเดล SARIMAX และคืนค่ากลางกับช่วงความเชื่อมั่น 95%
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        forecast_result = fitted_model.get_forecast(steps=steps, exog=future_exog)

    forecast_values = forecast_result.predicted_mean
    conf_int = forecast_result.conf_int(alpha=0.05)
    return forecast_values, conf_int


def extract_sarimax_feature_importance(fitted_model, exog_cols: Optional[List[str]] = None) -> List[dict]:
    """ดึงค่าสัมประสิทธิ์ (Coefficients), p-value และความสำคัญของตัวแปรภายนอก"""
    if not exog_cols:
        return []

    importance_list = []
    params = getattr(fitted_model, "params", {})
    pvalues = getattr(fitted_model, "pvalues", {})
    bse = getattr(fitted_model, "bse", {})

    for col in exog_cols:
        if col in params:
            coef = float(params[col])
            pval = float(pvalues[col]) if col in pvalues else None
            stderr = float(bse[col]) if col in bse else None
            # Absolute coefficient indicates relative impact scale
            importance_list.append({
                "feature": col,
                "coefficient": round(coef, 4),
                "p_value": round(pval, 4) if pval is not None else None,
                "std_err": round(stderr, 4) if stderr is not None else None,
                "is_significant": bool(pval is not None and pval < 0.05),
            })

    importance_list.sort(key=lambda x: abs(x["coefficient"]), reverse=True)
    return importance_list


def train_arima(train_df: pd.DataFrame, target_col: str, exog_cols: list, p: int, d: int, q: int):
    """
    ฝึกโมเดล ARIMA ตามลำดับ (p, d, q) จากคอลัมน์เป้าหมาย (Backward Compatible)
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
    พยากรณ์จำนวน steps จากโมเดลที่ฝึกแล้ว และคืนค่ากลางกับช่วงความเชื่อมั่น 95% (Backward Compatible)
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        forecast_result = fitted_model.get_forecast(steps=steps, exog=future_exog)

    forecast_values = forecast_result.predicted_mean
    conf_int = forecast_result.conf_int(alpha=0.05)  # 95% CI

    return forecast_values, conf_int


