import {readFileSync,writeFileSync} from 'node:fs'
import {loadEnv} from 'vite'
const mode=process.env.VITE_PUBLIC_DATA_MODE||loadEnv('production',process.cwd(),'VITE_').VITE_PUBLIC_DATA_MODE||'demo'
if(!['demo','api'].includes(mode))throw new Error('Invalid data mode')
const pattern=mode==='demo'?'(?:results(?:/autumn)?|competitions/(?:autumn|spring|archive)(?:/(?:schedule|standings|teams|rules|announcements|live))?|competitions/autumn/teams/[0-7]|matches/(?:featured|upcoming|upcoming-2)|announcements/[0-2])':'(?:results(?:/[^/]+)?|competitions/[^/]+(?:/(?:schedule|standings|teams|rules|announcements|live))?|competitions/[^/]+/teams/[^/]+|matches/[^/]+|announcements/[^/]+)'
const check=mode==='api'?`auth_request /_page_check;
error_page 403 =404 /404.html;
error_page 500 502 504 =503 /503.html;`:''
writeFileSync('nginx.generated.conf',readFileSync('nginx.conf','utf8').replace('__RESOURCE_LOCATION__',`location ~ ^/${pattern}$ {
${check}
try_files $uri /index.html;
}`))
const paths=['/','/competitions','/announcements','/results']
if(mode==='demo')for(const edition of ['autumn','spring','archive'])for(const tab of ['','/schedule','/standings','/teams','/rules'])paths.push('/competitions/'+edition+tab)
writeFileSync('dist/sitemap.xml','<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+paths.map(p=>'<url><loc>https://www.gdufcs.fun'+p+'</loc></url>').join('')+'</urlset>')
