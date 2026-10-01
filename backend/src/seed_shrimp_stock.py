import asyncio
import os
import sys
import datetime
import random
import logging

# Ensure backend/src is in python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from db.database import SessionLocal
from models.stock import ShrimpStockData

async def seed_data():
    product = "Premium_White_Shrimp"
    print(f"Seeding mock data for {product}...")
    async with SessionLocal() as session:
        # Clear existing data for this product
        # Note: We won't clear to keep it simple, just add 60 days up to today
        
        today = datetime.datetime.now(datetime.timezone.utc)
        inventory = 1000.0
        
        for i in range(60, 0, -1):
            date = today - datetime.timedelta(days=i)
            # Add some random walk
            change = random.uniform(-100, 120)
            inventory = max(100.0, inventory + change)
            
            stock = ShrimpStockData(
                recorded_at=date,
                product=product,
                quantity=round(inventory, 2),
                unit="kg",
                warehouse="Main_Warehouse",
                source="mock_seed"
            )
            session.add(stock)
            
        await session.commit()
    print("Seeding complete! You can now run the ARIMA forecast.")

if __name__ == "__main__":
    asyncio.run(seed_data())
