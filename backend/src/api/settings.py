"""API สำหรับอ่านและอัปเดตค่า setting ของระบบ เช่น risk preference และ threshold.

ข้อมูลถูกเก็บในตาราง system_settings เพื่อให้ frontend/backend ใช้ค่าเดียวกันและสามารถปรับพฤติกรรม
ของการประเมินความเสี่ยงได้แบบ dynamic.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Dict, Any

from db.database import get_db_session
from models.stock import SystemSetting

router = APIRouter(prefix="/settings", tags=["settings"])

class SettingsUpdate(BaseModel):
    settings: Dict[str, str]

@router.get("", response_model=Dict[str, str])
async def get_all_settings(session: AsyncSession = Depends(get_db_session)):
    stmt = select(SystemSetting)
    result = await session.execute(stmt)
    settings_dict = {}
    for s in result.scalars().all():
        settings_dict[s.key] = s.value
        
    # Default fallback for important settings if missing
    defaults = {
        "risk_preference": "balanced",
        "low_stock_threshold": "1000",
        "forecast_horizon": "3",
        "default_product": "tiger_shrimp_size_L"
    }
    for k, v in defaults.items():
        if k not in settings_dict:
            settings_dict[k] = v
            
    return settings_dict

@router.put("", response_model=Dict[str, str])
async def update_settings(data: SettingsUpdate, session: AsyncSession = Depends(get_db_session)):
    stmt = select(SystemSetting)
    result = await session.execute(stmt)
    existing_settings = {s.key: s for s in result.scalars().all()}
    
    for key, value in data.settings.items():
        if key in existing_settings:
            existing_settings[key].value = str(value)
        else:
            new_setting = SystemSetting(key=key, value=str(value), description=f"Updated {key}")
            session.add(new_setting)
            
    await session.commit()
    
    # Fetch updated
    result = await session.execute(select(SystemSetting))
    return {s.key: s.value for s in result.scalars().all()}
