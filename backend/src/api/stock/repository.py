"""Database queries for inventory summaries."""

from datetime import date
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.stock import InventorySummary


class StockRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_stocks(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        split: Optional[str] = None,
        time: Optional[str] = None,
    ) -> list[InventorySummary]:
        stmt = select(InventorySummary)
        if start_date:
            stmt = stmt.where(InventorySummary.date >= start_date)
        if end_date:
            stmt = stmt.where(InventorySummary.date <= end_date)
        if split:
            stmt = stmt.where(InventorySummary.split == split)
        if time:
            stmt = stmt.where(InventorySummary.time == time)

        stmt = stmt.order_by(InventorySummary.date.desc(), InventorySummary.time.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_summary(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        split: Optional[str] = None,
        time: Optional[str] = None,
    ) -> dict:
        filters = []
        if start_date:
            filters.append(InventorySummary.date >= start_date)
        if end_date:
            filters.append(InventorySummary.date <= end_date)
        if split:
            filters.append(InventorySummary.split == split)
        if time:
            filters.append(InventorySummary.time == time)

        latest_stmt = (
            select(InventorySummary.total_boxes)
            .where(*filters)
            .order_by(InventorySummary.date.desc(), InventorySummary.time.desc())
            .limit(1)
        )
        stmt = select(
            latest_stmt.scalar_subquery(),
            func.avg(InventorySummary.total_boxes),
            func.min(InventorySummary.total_boxes),
            func.max(InventorySummary.total_boxes),
            func.max(InventorySummary.date),
            func.count(InventorySummary.id),
        )
        if filters:
            stmt = stmt.where(*filters)

        result = await self.session.execute(stmt)
        row = result.one()
        return {
            "current_stock": row[0] or 0.0,
            "average_stock": row[1] or 0.0,
            "minimum_stock": row[2] or 0.0,
            "maximum_stock": row[3] or 0.0,
            "latest_record": row[4],
            "number_of_records": row[5] or 0,
        }

    async def get_splits(self) -> list[str]:
        stmt = select(InventorySummary.split).distinct().order_by(InventorySummary.split)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_existing_keys(self, records: list[dict]) -> set[tuple]:
        if not records:
            return set()

        conditions = [
            and_(
                InventorySummary.date == record["date"],
                InventorySummary.split == record["split"],
                InventorySummary.time == record["time"],
            )
            for record in records
        ]
        stmt = select(
            InventorySummary.date,
            InventorySummary.split,
            InventorySummary.time,
        ).where(or_(*conditions))
        result = await self.session.execute(stmt)
        return {tuple(row) for row in result.all()}

    async def bulk_insert(self, records: list[InventorySummary]) -> None:
        self.session.add_all(records)
        await self.session.commit()
