# Inventory CSV files

- `shrimp_stock_6years_mont.csv`: monthly records
- `shrimp_stock_daily_6years.csv`: daily records

ทั้งสองไฟล์มี headers `time,product,boxes_A,boxes_B,total_boxes`. `scripts/import_inventory_csv.py` อ่านไฟล์เหล่านี้; `workers/inventory_data.py` ไม่ได้เลือกชื่อไฟล์ทั้งสองเป็น default seed paths.
