import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  // ปลั๊กอิน React แปลง JSX/TSX และรองรับการอัปเดตหน้าแบบ Fast Refresh ระหว่างพัฒนา
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        // ใช้ชื่อ service ที่ Docker Compose ทำ DNS ให้; ถ้าใช้ localhost จะชี้กลับมาที่ frontend เอง
        target: 'http://backend:8000',
        changeOrigin: true
      }
    }
  }
})
