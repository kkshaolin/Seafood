// คอมโพเนนต์รากของ React ปัจจุบันแสดง Dashboard เป็นหน้าหลักของระบบ
import React from 'react'
import { Dashboard } from './components/Dashboard'

// แยกโครงหน้าหลักไว้ตรงนี้ เพื่อเพิ่มเมนูหรือหน้าจออื่นได้โดยไม่ต้องแก้จุดเริ่มโปรแกรม
function App() {
  return (
    <Dashboard />
  )
}

export default App
