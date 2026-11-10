import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig(({mode})=>({plugins:[vue()],define:{'import.meta.env.VITE_PUBLIC_DATA_MODE':JSON.stringify(process.env.VITE_PUBLIC_DATA_MODE||loadEnv(mode,process.cwd(),'VITE_').VITE_PUBLIC_DATA_MODE||'api')},server:{proxy:{'/api':process.env.VITE_API_PROXY||'http://127.0.0.1:8000','/media':process.env.VITE_API_PROXY||'http://127.0.0.1:8000'}}}))
