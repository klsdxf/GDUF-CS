import {defineConfig} from '@playwright/test'
export default defineConfig({testDir:'./tests',fullyParallel:true,timeout:60000,use:{baseURL:'http://localhost:5173',browserName:'chromium',channel:process.platform==='win32'?'msedge':undefined},reporter:[['list'],['html',{open:'never'}]],webServer:[
 {command:'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort',env:{VITE_PUBLIC_DATA_MODE:'demo'},url:'http://localhost:5173',reuseExistingServer:!process.env.CI},
 {command:'npm run dev -- --host 127.0.0.1 --port 5176 --strictPort',env:{VITE_PUBLIC_DATA_MODE:'api'},url:'http://127.0.0.1:5176',reuseExistingServer:!process.env.CI},
 {command:'node tests/reference-server.mjs',url:'http://127.0.0.1:4175',reuseExistingServer:!process.env.CI}
]})
