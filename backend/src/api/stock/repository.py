"""Repository layer สำหรับติดต่อฐานข้อมูลของตาราง shrimp_stocks.

ทำหน้าที่สร้าง query สำหรับ filter ข้อมูล, summary, product list, duplicate check และ bulk insert
เพื่อให้ controller ใช้งานได้โดยไม่ต้องเขียน SQL ตรง ๆ ใน endpoint.
"""

from datetime import datetime, date
from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from models.stock import ShrimpStockData


class StockRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_stocks(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        product: Optional[str] = None,
        warehouse: Optional[str] = None
    ) -> List[ShrimpStockData]:
        stmt = select(ShrimpStockData)
        if start_date:
            stmt = stmt.where(ShrimpStockData.recorded_at >= start_date)
        if end_date:
            stmt = stmt.where(ShrimpStockData.recorded_at <= end_date)
        if product:
            stmt = stmt.where(ShrimpStockData.product == product)
        if warehouse:
            stmt = stmt.where(ShrimpStockData.warehouse == warehouse)
            
        stmt = stmt.order_by(ShrimpStockData.recorded_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_summary(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        product: Optional[str] = None,
        warehouse: Optional[str] = None
    ) -> dict:
        stmt = select(
            func.sum(ShrimpStockData.quantity),
            func.avg(ShrimpStockData.quantity),
            func.min(ShrimpStockData.quantity),
            func.max(ShrimpStockData.quantity),
            func.max(ShrimpStockData.recorded_at),
            func.count(ShrimpStockData.id)
        )
        if start_date:
            stmt = stmt.where(ShrimpStockData.recorded_at >= start_date)
        if end_date:
            stmt = stmt.where(ShrimpStockData.recorded_at <= end_date)
        if product:
            stmt = stmt.where(ShrimpStockData.product == product)
        if warehouse:
            stmt = stmt.where(ShrimpStockData.warehouse == warehouse)

        result = await self.session.execute(stmt)
        row = result.first()
        
        return {
            "current_stock": row[0] if row[0] is not None else 0.0, # using sum for current stock inside period
            "average_stock": row[1] if row[1] is not None else 0.0,
            "minimum_stock": row[2] if row[2] is not None else 0.0,
            "maximum_stock": row[3] if row[3] is not None else 0.0,
            "latest_record": row[4],
            "number_of_records": row[5] if row[5] is not None else 0
        }

    async def get_products(self) -> List[str]:
        stmt = select(ShrimpStockData.product).distinct()
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def check_duplicate(self, recorded_at: datetime, product: str, warehouse: Optional[str]) -> bool:
        stmt = select(ShrimpStockData.id).where(
            and_(
                ShrimpStockData.recorded_at == recorded_at,
                ShrimpStockData.product == product,
                ShrimpStockData.warehouse == warehouse
            )
        ).limit(1)
        result = await self.session.execute(stmt)
        return result.first() is not None

    async def get_existing_keys(self, records: List[dict]) -> set:
        """
        ดึงข้อมูล key (recorded_at, product, warehouse) ที่มีอยู่แล้วในฐานข้อมูล 
        เพื่อใช้ตรวจสอบ Duplicate แบบ Bulk ช่วยลดปัญหา N+1 Query
        """
        if not records:
            return set()
            
        # สร้างเงื่อนไขจาก records ที่ส่งเข้ามา
        conditions = []
        for r in records:
            conditions.append(
                and_(
                    ShrimpStockData.recorded_at == r["recorded_at"],
                    ShrimpStockData.product == r["product"],
                    ShrimpStockData.warehouse == r["warehouse"]
                )
            )
            
        # ใช้ or_ เพื่อรวบรวมเงื่อนไขทั้งหมด (ใช้ or_() ใน SQLAlchemy)
        from sqlalchemy import or_
        stmt = select(ShrimpStockData.recorded_at, ShrimpStockData.product, ShrimpStockData.warehouse).where(
            or_(*conditions)
        )
        result = await self.session.execute(stmt)
        return set(result.all())

    async def bulk_insert(self, records: List[ShrimpStockData]):
        self.session.add_all(records)
        await self.session.commit()
