import {existsSync} from 'node:fs'
import {resolve} from 'node:path'
import {defineConfig} from '@playwright/test'
process.env.RESULTS_LIVE_E2E='1'
const apiUrl='http://127.0.0.1:'+(process.env.RESULTS_API_PORT||'5186')
const webPort=process.env.RESULTS_WEB_PORT||'5187'
const webUrl='http://localhost:'+webPort
export default defineConfig({testDir:'./tests',testMatch:'results-live.spec.ts',workers:1,timeout:60000,use:{baseURL:webUrl,channel:process.platform==='win32'?'msedge':undefined,video:'retain-on-failure',trace:'retain-on-failure'},webServer:[
 {command:(process.platform==='win32'&&existsSync('../.venv/Scripts/python.exe')?'\"'+resolve('../.venv/Scripts/python.exe')+'\"':'python')+' -m tests.results_e2e_server',cwd:'../backend',url:apiUrl+'/api/v1/health'},
 {command:'npm run dev -- --host 127.0.0.1 --port '+webPort+' --strictPort',env:{VITE_PUBLIC_DATA_MODE:'api',VITE_API_PROXY:apiUrl},url:webUrl}
]})
