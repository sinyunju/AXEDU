import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 같은 Wi-Fi의 휴대폰·태블릿에서도 접속할 수 있게 (http://이 PC의 IP:5173)
    host: true,
    port: 5173,
  },
})
