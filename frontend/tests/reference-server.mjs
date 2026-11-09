// Serves only the immutable approved design, on loopback, for visual comparisons.
import http from 'node:http'
import fs from 'node:fs/promises'
import path from 'node:path'
const root=path.resolve('../开发文档/前端设计基准/GDUFCS_2026重设计_已确认')
const types={'.html':'text/html','.css':'text/css','.js':'text/javascript','.jpg':'image/jpeg','.woff2':'font/woff2'}
http.createServer(async(req,res)=>{try{const url=new URL(req.url,'http://127.0.0.1');if(url.pathname==='/results-v6'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(await fs.readFile('../开发文档/最终排名更新/GDUFCS_最终排名_技术开发交付包_V1.0/reference/index.html'));return}const file=path.resolve(root,'.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname));if(!file.startsWith(root+path.sep))throw Error();const content=await fs.readFile(file);res.setHeader('Content-Type',(types[path.extname(file)]||'application/octet-stream')+'; charset=utf-8');res.end(content)}catch{res.statusCode=404;res.end('Not found')}}).listen(4175,'127.0.0.1')
