"""Service สำหรับคำนวณระดับความเสี่ยงของสต็อกแบบง่ายและ determinist.

ผลลัพธ์นี้แสดงสถานะ Normal / Warning / Critical ตาม threshold ที่ปรับตาม risk preference
และใช้โดย API /risk/evaluate ให้ frontend จัดการข้อความแจ้งเตือนได้ทันที.
"""

class RiskService:
    @staticmethod
    def evaluate_risk(current_stock: float, forecast_stock: float, threshold: float, risk_preference: str) -> dict:
        """
        Evaluate stock risk based on deterministic rules and risk preference.
        """
        preference = risk_preference.lower()
        
        # Determine actual threshold buffer based on preference
        if preference == "conservative":
            # Wants more stock, alerts earlier (e.g., 20% buffer)
            effective_threshold = threshold * 1.2
        elif preference == "aggressive":
            # Comfortable with leaner stock, alerts later (e.g., 20% tolerance below threshold)
            effective_threshold = threshold * 0.8
        else:
            # Balanced / Default
            effective_threshold = threshold
            
        risk_level = "Normal"
        reason = "Stock levels are projected to be healthy."
        
        if forecast_stock <= 0:
            risk_level = "Critical"
            reason = f"Projected stock is fully depleted (0 kg). Immediate restocking required."
        elif forecast_stock < effective_threshold:
            if forecast_stock < (effective_threshold * 0.5):
                risk_level = "Critical"
                reason = f"Forecast ({forecast_stock:.0f}) is critically below the effective threshold ({effective_threshold:.0f}) under '{preference}' preference."
            else:
                risk_level = "Warning"
                reason = f"Forecast ({forecast_stock:.0f}) falls below the effective threshold ({effective_threshold:.0f}) under '{preference}' preference."
        elif current_stock < effective_threshold and forecast_stock >= effective_threshold:
            risk_level = "Normal"
            reason = "Current stock is low, but projected forecast indicates a recovery above threshold."
            
        return {
            "risk_level": risk_level,
            "current_stock": current_stock,
            "forecast_stock": forecast_stock,
            "threshold": threshold,
            "effective_threshold": effective_threshold,
            "risk_preference": preference,
            "reason": reason
        }
