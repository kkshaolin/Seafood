"""Compatibility command for importing the inventory CSV into PostgreSQL."""

import asyncio
import sys
from pathlib import Path

workers_dir = Path(__file__).resolve().parents[2] / "workers"
sys.path.insert(0, str(workers_dir))

from seed_inventory import main


if __name__ == "__main__":
    asyncio.run(main())
