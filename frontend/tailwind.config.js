/** @type {import('tailwindcss').Config} */
export default {
  // ระบุไฟล์ที่ Tailwind ต้องสแกน เพื่อสร้างเฉพาะ utility classes ที่ UI ใช้จริง
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
