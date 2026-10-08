# Public assets

`mockA.mp4` และ `mockB.mp4` เป็นวิดีโอ mock ที่ Vite/Nginx เสิร์ฟเป็น static assets และ Dashboard ใช้แสดงเป็น source ภาพ Zone A/Zone B. Sampling worker และ camera API มี path lookup ที่อาจอ่านวิดีโอเหล่านี้เมื่อทำงานจาก checkout/container ตามตำแหน่ง mount.
