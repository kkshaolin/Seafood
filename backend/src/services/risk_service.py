"""Service สำหรับคำนวณระดับความเสี่ยงของสต็อกแบบเปรียบเทียบค่าทำนายกับค่าตรวจจับจากกล้อง.

ผลลัพธ์นี้แสดงสถานะ Normal / Warning / Critical ตามเกณฑ์ความคลาดเคลื่อนและ threshold
ที่ปรับตาม risk preference และใช้โดย API /risk/evaluate ให้ frontend จัดการข้อความแจ้งเตือนได้ทันที.
"""

from typing import Optional, Dict, Any


class RiskService:
    @staticmethod
    def evaluate_risk(
        current_stock: float = 0.0,
        forecast_stock: float = 0.0,
        threshold: float = 0.0,
        risk_preference: str = "balanced",
        detected_stock: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        ประเมินความเสี่ยงสต็อก:
        1. หากมีค่าที่ตรวจจับได้จากกล้อง (detected_stock): เปรียบเทียบระหว่างค่าตรวจพบจริง (CCTV/YOLO) กับค่าทำนาย (ARIMA Forecast)
        2. หากไม่มีข้อมูลกล้อง: เปรียบเทียบค่าทำนายกับเกณฑ์ปลอดภัย (Safety Threshold)
        """
        preference = (risk_preference or "balanced").lower()

        # กำหนดช่วงยอมรับความคลาดเคลื่อนตาม Risk Preference
        # Conservative (เข้มงวด): เตือนเมื่อต่างกัน > 10%, วิกฤตเมื่อต่างกัน > 20%
        # Balanced (มาตรฐาน): เตือนเมื่อต่างกัน > 15%, วิกฤตเมื่อต่างกัน > 30%
        # Aggressive (ยืดหยุ่น): เตือนเมื่อต่างกัน > 25%, วิกฤตเมื่อต่างกัน > 45%
        if preference == "conservative":
            warn_pct = 10.0
            crit_pct = 20.0
            effective_threshold = threshold * 1.2
        elif preference == "aggressive":
            warn_pct = 25.0
            crit_pct = 45.0
            effective_threshold = threshold * 0.8
        else:
            preference = "balanced"
            warn_pct = 15.0
            crit_pct = 30.0
            effective_threshold = threshold

        diff_percent: Optional[float] = None

        if detected_stock is not None:
            # --- โหมดเปรียบเทียบค่าตรวจพบจริง (Detected) กับค่าทำนาย (Forecast) ---
            if forecast_stock <= 0:
                risk_level = "Critical"
                reason = "ยอดพยากรณ์เป็น 0 พาเลท (สต็อกหมดคลัง) จำเป็นต้องสั่งสินค้าเข้าคลังทันที"
            elif detected_stock <= 0 and forecast_stock > 0:
                risk_level = "Critical"
                reason = f"ตรวจไม่พบพาเลทจากกล้อง (0 พาเลท) ขณะที่ยอดทำนายคือ {forecast_stock:.0f} พาเลท เสี่ยงสินค้าสูญหายหรือกล้องขัดข้อง"
            else:
                diff = detected_stock - forecast_stock
                diff_pct = (abs(diff) / forecast_stock) * 100.0 if forecast_stock > 0 else 0.0
                diff_percent = round(diff_pct, 1)

                if diff_pct > crit_pct:
                    risk_level = "Critical"
                    if diff < 0:
                        reason = f"ตรวจพบ {detected_stock:.0f} พาเลท ต่ำกว่ายอดทำนาย {forecast_stock:.0f} พาเลท ({diff_pct:.1f}%) วิกฤต: เสี่ยงสินค้าขาดคลังหรือสูญหาย"
                    else:
                        reason = f"ตรวจพบ {detected_stock:.0f} พาเลท สูงกว่ายอดทำนาย {forecast_stock:.0f} พาเลท ({diff_pct:.1f}%) วิกฤต: สต็อกล้นคลังเกินคาดการณ์"
                elif diff_pct > warn_pct:
                    risk_level = "Warning"
                    if diff < 0:
                        reason = f"ตรวจพบ {detected_stock:.0f} พาเลท ต่ำกว่ายอดทำนาย {forecast_stock:.0f} พาเลท ({diff_pct:.1f}%) เฝ้าระวัง: สินค้าหน้างานเริ่มพร่อง"
                    else:
                        reason = f"ตรวจพบ {detected_stock:.0f} พาเลท สูงกว่ายอดทำนาย {forecast_stock:.0f} พาเลท ({diff_pct:.1f}%) เฝ้าระวัง: พื้นที่จัดเก็บเริ่มหนาแน่น"
                else:
                    risk_level = "Normal"
                    reason = f"ตรวจพบ {detected_stock:.0f} พาเลท สอดคล้องกับยอดทำนาย {forecast_stock:.0f} พาเลท (ต่างกัน {diff_pct:.1f}%) สต็อกหน้างานอยู่ในเกณฑ์ปกติ"
        else:
            # --- โหมดดั้งเดิม (กรณีไม่มีข้อมูลจากกล้อง): เทียบ forecast_stock กับ effective_threshold ---
            if forecast_stock <= 0:
                risk_level = "Critical"
                reason = "ยอดพยากรณ์เป็น 0 พาเลท (สต็อกหมดคลัง) จำเป็นต้องสั่งสินค้าเข้าคลังทันที"
            elif effective_threshold > 0 and forecast_stock < effective_threshold:
                if forecast_stock < (effective_threshold * 0.5):
                    risk_level = "Critical"
                    reason = f"ยอดทำนาย ({forecast_stock:.0f} พาเลท) ต่ำกว่าเกณฑ์ความปลอดภัย ({effective_threshold:.0f} พาเลท) อย่างวิกฤต"
                else:
                    risk_level = "Warning"
                    reason = f"ยอดทำนาย ({forecast_stock:.0f} พาเลท) ต่ำกว่าเกณฑ์ความปลอดภัย ({effective_threshold:.0f} พาเลท)"
            elif current_stock < effective_threshold and forecast_stock >= effective_threshold:
                risk_level = "Normal"
                reason = "สต็อกปัจจุบันต่ำกว่าเกณฑ์ แต่ยอดพยากรณ์คาดว่าจะฟื้นตัวกลับสู่ระดับปลอดภัย"
            else:
                risk_level = "Normal"
                reason = "ระดับสต็อกคาดการณ์อยู่ในเกณฑ์ปลอดภัย"

        return {
            "risk_level": risk_level,
            "current_stock": current_stock,
            "forecast_stock": forecast_stock,
            "detected_stock": detected_stock,
            "diff_percent": diff_percent,
            "threshold": threshold,
            "effective_threshold": effective_threshold,
            "risk_preference": preference,
            "reason": reason
        }
