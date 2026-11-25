import http.server, json, base64, sys, zlib, struct, os, threading
PORT=int(sys.argv[1]); MP4F=sys.argv[2]; COVF=sys.argv[3]; REPO=sys.argv[4]
def png():
    w=h=64; raw=b''
    for y in range(h):
        raw+=b'\0'
        for x in range(w):
            raw+= bytes((0xE8,0xB8,0x4B,255)) if (x-32)**2+(y-32)**2<900 else bytes((0,0,0,0))
    def ch(t,d): c=struct.pack('>I',len(d))+t+d; return c+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+ch(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+ch(b'IDAT',zlib.compress(raw))+ch(b'IEND',b'')
PNG=png()
import zipfile, io, random
MP4=open(MP4F,'rb').read(); PNG_COVER=open(COVF,'rb').read()
zb=io.BytesIO()
with zipfile.ZipFile(zb,'w',zipfile.ZIP_STORED) as z: z.writestr('output.mp4',MP4); z.writestr('cover.png',PNG_COVER)
ZIP=zb.getvalue()
brand_text=open(REPO+'/studio/brand-config.json',encoding='utf8').read(); brand=json.loads(brand_text)
B64=base64.b64encode(brand_text.encode()).decode()
LOG=[]; BODIES=[]; HITS=[0]
class H(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*a): pass
    def out(self,code,body=b'',ct='application/json',extra=None):
        if isinstance(body,str): body=body.encode()
        self.send_response(code); self.send_header('Content-Type',ct); self.send_header('Content-Length',str(len(body)))
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)
    def body(self):
        n=int(self.headers.get('Content-Length') or 0); return self.rfile.read(n)
    def do_ANY(self):
        m=self.command; p=self.path.split('?')[0]; q=self.path.partition('?')[2]; auth=self.headers.get('Authorization')
        if p=='/__log': return self.out(200,json.dumps({"log":LOG,"bodies":BODIES,"hits":HITS[0]}))
        if p=='/__reset': LOG.clear(); BODIES.clear(); HITS[0]=0; return self.out(200,'{}')
        LOG.append(m+' '+p)
        R='/repo'
        if p==R: return self.out(200,'{"default_branch":"main"}')
        if p==R+'/contents/studio/brand-config.json' and m=='GET': return self.out(200,json.dumps({"sha":"SHA1","content":B64}))
        if p==R+'/contents/studio/brand-config.json' and m=='PUT':
            b=self.body().decode()
            if auth!='Bearer WRITE': return self.out(403,'{"message":"Resource not accessible"}')
            BODIES.append('PUT-brand '+b); return self.out(200,'{}')
        if p.startswith(R+'/contents/assets/logo/') and m=='GET':
            fp=REPO+'/assets/logo/'+p.split('/')[-1]
            return self.out(200,open(fp,'rb').read() if os.path.exists(fp) else PNG,'image/png')
        if p.startswith(R+'/contents/assets/logo/') and m=='PUT':
            self.body(); return self.out(201 if auth=='Bearer WRITE' else 403,'{}')
        if p==R+'/actions/workflows/produce.yml/runs':
            return self.out(200,json.dumps({"workflow_runs":[{"id":112,"status":"in_progress","conclusion":None,"display_title":"Produce  gm1-aaa","created_at":"2026-11-25T10:00:00Z"},{"id":111,"status":"completed","conclusion":"success","display_title":"Produce  gm1-bbb","created_at":"2026-11-25T09:00:00Z"}]}))
        if p==R+'/actions/artifacts' and m=='GET':
            return self.out(200,json.dumps({"artifacts":[{"id":9,"name":"video-81","size_in_bytes":len(ZIP),"expired":False,"created_at":"2026-11-25T09:05:00Z","workflow_run":{"id":111}}]}))
        if p==R+'/actions/artifacts/9/zip': return self.out(302,b'',extra={'Location':'http://127.0.0.1:%d/blob/9'%PORT})
        if p=='/blob/9':
            HITS[0]+=1; rg=self.headers.get('Range')
            if not rg:
                self.send_response(200); self.send_header('Content-Length',str(len(ZIP))); self.end_headers()
                self.wfile.write(ZIP[:len(ZIP)//2]); self.wfile.flush(); self.close_connection=True; self.connection.close(); return
            f=int(rg.replace('bytes=','').replace('-',''))
            return self.out(206,ZIP[f:],'application/zip',{'Content-Range':'bytes %d-%d/%d'%(f,len(ZIP)-1,len(ZIP))})
        if p==R+'/actions/workflows/produce.yml/dispatches': BODIES.append('DISPATCH '+self.body().decode()); return self.out(204)
        if p==R+'/actions/artifacts/9' and m=='DELETE': return self.out(204)
        if p==R+'/releases/tags/uploads': return self.out(200,'{"id":5}')
        if p.startswith('/up/repos/') and m=='POST':
            b=self.body(); BODIES.append('UPLOAD %d %s'%(len(b),q)); return self.out(201,'{"id":77,"browser_download_url":"https://github.com/dl/u-test.mp4"}')
        if p==R+'/releases/assets/77' and m=='DELETE': return self.out(204)
        return self.out(404,json.dumps({"message":"nf "+p}))
    do_GET=do_POST=do_PUT=do_DELETE=do_PATCH=do_ANY
http.server.ThreadingHTTPServer(('127.0.0.1',PORT),H).serve_forever()
