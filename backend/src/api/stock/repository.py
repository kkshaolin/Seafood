"""Database queries for monthly and daily inventories."""

from datetime import date
from typing import Optional

from sqlalchemy import and_, func, or_, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from models.stock import MonthlyInventory, DailyInventory, InventorySummary


class StockRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_stocks(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        product: Optional[str] = None,
        split: Optional[str] = None,
        time: Optional[str] = None,
    ) -> list[MonthlyInventory]:
        stmt = select(MonthlyInventory)
        if start_date:
            stmt = stmt.where(MonthlyInventory.time >= start_date)
        if end_date:
            stmt = stmt.where(MonthlyInventory.time <= end_date)
        if product:
            stmt = stmt.where(or_(MonthlyInventory.product == product, MonthlyInventory.product == "Frozen Shrimp"))

        stmt = stmt.order_by(MonthlyInventory.time.desc())
        result = await self.session.execute(stmt)
        records = list(result.scalars().all())
        if records:
            return records

        # Fallback to old inventory_summaries if monthly_inventories is empty
        stmt_old = select(InventorySummary).order_by(InventorySummary.date.desc())
        res_old = await self.session.execute(stmt_old)
        return list(res_old.scalars().all())

    async def get_summary(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        product: Optional[str] = None,
        split: Optional[str] = None,
        time_val: Optional[str] = None,
    ) -> dict:
        filters = []
        if start_date:
            filters.append(MonthlyInventory.time >= start_date)
        if end_date:
            filters.append(MonthlyInventory.time <= end_date)
        if product:
            filters.append(or_(MonthlyInventory.product == product, MonthlyInventory.product == "Frozen Shrimp"))

        latest_stmt = (
            select(MonthlyInventory.total_boxes)
            .where(*filters)
            .order_by(MonthlyInventory.time.desc())
            .limit(1)
        )
        stmt = select(
            latest_stmt.scalar_subquery(),
            func.avg(MonthlyInventory.total_boxes),
            func.min(MonthlyInventory.total_boxes),
            func.max(MonthlyInventory.total_boxes),
            func.max(MonthlyInventory.time),
            func.count(MonthlyInventory.id),
        )
        if filters:
            stmt = stmt.where(*filters)

        result = await self.session.execute(stmt)
        row = result.one()
        
        # If no records in monthly_inventories, fallback
        if not row[5]:
            stmt_old = select(
                func.avg(InventorySummary.total_boxes),
                func.min(InventorySummary.total_boxes),
                func.max(InventorySummary.total_boxes),
                func.max(InventorySummary.date),
                func.count(InventorySummary.id),
            )
            res_old = await self.session.execute(stmt_old)
            row_old = res_old.one()
            return {
                "current_stock": row_old[0] or 0.0,
                "average_stock": round(float(row_old[0] or 0.0), 2),
                "minimum_stock": row_old[1] or 0.0,
                "maximum_stock": row_old[2] or 0.0,
                "latest_record": row_old[3],
                "number_of_records": row_old[4] or 0,
            }

        return {
            "current_stock": float(row[0] or 0.0),
            "average_stock": round(float(row[1] or 0.0), 2),
            "minimum_stock": float(row[2] or 0.0),
            "maximum_stock": float(row[3] or 0.0),
            "latest_record": row[4],
            "number_of_records": row[5] or 0,
        }

    async def get_products(self) -> list[str]:
        stmt = select(MonthlyInventory.product).distinct().order_by(MonthlyInventory.product)
        result = await self.session.execute(stmt)
        prods = list(result.scalars().all())
        if prods:
            return prods
        return ["Frozen Shrimp"]

    async def get_history(
        self,
        product: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[MonthlyInventory]:
        stmt = select(MonthlyInventory)
        if product:
            stmt = stmt.where(or_(MonthlyInventory.product == product, MonthlyInventory.product == "Frozen Shrimp"))
        if start_date:
            stmt = stmt.where(MonthlyInventory.time >= start_date)
        if end_date:
            stmt = stmt.where(MonthlyInventory.time <= end_date)

        stmt = stmt.order_by(MonthlyInventory.time.asc())
        result = await self.session.execute(stmt)
        records = list(result.scalars().all())
        return records

    async def get_splits(self) -> list[str]:
        return ["Zone A", "Zone B", "All Zones"]

    async def bulk_insert_monthly(self, records: list[MonthlyInventory]) -> None:
        self.session.add_all(records)
        await self.session.commit()
