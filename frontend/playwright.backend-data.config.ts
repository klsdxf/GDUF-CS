import {existsSync} from 'node:fs'
import {resolve} from 'node:path'
import {defineConfig} from '@playwright/test'
process.env.BACKEND_DATA_E2E='1'
export default defineConfig({outputDir:'./test-results/backend-data',testDir:'./tests',testMatch:'backend-data.spec.ts',workers:1,timeout:120000,use:{baseURL:'http://localhost:5191',channel:process.platform==='win32'?'msedge':undefined,video:'retain-on-failure',trace:'retain-on-failure'},webServer:[
 {command:(process.platform==='win32'&&existsSync('../.venv/Scripts/python.exe')?'"'+resolve('../.venv/Scripts/python.exe')+'"':'python')+' -m tests.backend_data_e2e_server',cwd:'../backend',url:'http://127.0.0.1:5190/api/v1/health'},
 {command:'npm run dev -- --host 127.0.0.1 --port 5191 --strictPort',env:{VITE_PUBLIC_DATA_MODE:'api',VITE_API_PROXY:'http://127.0.0.1:5190'},url:'http://localhost:5191'}
]})
