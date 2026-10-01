// จุดเริ่มต้นบนเบราว์เซอร์: นำ React app ไปแสดงใน element ที่เตรียมไว้ใน index.html
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

// StrictMode ช่วยเตือนรูปแบบการใช้ lifecycle ที่เสี่ยงต่อบั๊กระหว่างพัฒนา โดยไม่เปลี่ยน UI ที่ผู้ใช้เห็น
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
