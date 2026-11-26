import http.server, json, sys, io, zipfile, subprocess, time, threading, os
PORT=int(sys.argv[1]); R='/repo'
subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i','sine=frequency=330:duration=3','-codec:a','libmp3lame','/tmp/c1.mp3'])
subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i','sine=frequency=550:duration=2','-codec:a','libmp3lame','/tmp/c2.mp3'])
C1=open('/tmp/c1.mp3','rb').read(); C2=open('/tmp/c2.mp3','rb').read()
zb=io.BytesIO()
with zipfile.ZipFile(zb,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('alt/',b''); z.writestr('alt/alt_x_s1000_k0.wav',os.urandom(600000)); z.writestr('clip_01.wav',os.urandom(300000))
    z.writestr('clip_01.mp3',C1); z.writestr('clip_02.mp3',C2); z.writestr('timings.json','{}')
ZIP=zb.getvalue()
RUNS={}; LOG=[]; BODIES=[]; NEXT=[500]
class H(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*a): pass
    def out(self,code,body=b'',ct='application/json',extra=None):
        if isinstance(body,str): body=body.encode()
        self.send_response(code); self.send_header('Content-Type',ct); self.send_header('Content-Length',str(len(body)))
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)
    def do_ANY(self):
        m=self.command; p=self.path.split('?')[0]; auth=self.headers.get('Authorization'); n=int(self.headers.get('Content-Length') or 0); b=self.rfile.read(n) if n else b''
        if p=='/__log': return self.out(200,json.dumps({"log":LOG[-80:],"bodies":BODIES}))
        LOG.append(m+' '+p+' auth='+str(auth))
        if p==R+'/actions/workflows/tts.yml/dispatches' and m=='POST':
            if auth!='Bearer READ': return self.out(403,'{}')
            d=json.loads(b); i=d['inputs']; BODIES.append('DISPATCH ref=%s mode=%s voice=%s best_of=%s req=%s text=%s'%(d['ref'],i['mode'],i['voice'],i['best_of'],i['request_id'],i['text'][:40]))
            rid=NEXT[0]; NEXT[0]+=1; RUNS[rid]={"id":rid,"req":i['request_id'],"polls":0,"fail":('FAIL' in i['text'] and not i['request_id'].endswith('r1'))}
            return self.out(204)
        if p==R+'/actions/workflows/tts.yml/runs':
            return self.out(200,json.dumps({"workflow_runs":[{"id":r["id"],"display_title":"nile-tts "+r["req"],"event":"workflow_dispatch"} for r in sorted(RUNS.values(),key=lambda x:-x['id'])]}))
        if p.startswith(R+'/actions/runs/') and p.endswith('/cancel'): BODIES.append('CANCEL '+p); return self.out(202,'{}')
        if p.startswith(R+'/actions/runs/') and p.endswith('/artifacts'):
            rid=int(p.split('/')[-2]); return self.out(200,json.dumps({"artifacts":[{"id":rid*10,"name":"tts-%s-%d"%(RUNS[rid]['req'],rid),"expired":False}]}))
        if p.startswith(R+'/actions/runs/') and m=='GET':
            rid=int(p.split('/')[-1]); r=RUNS[rid]; r['polls']+=1
            st='queued' if r['polls']<2 else 'in_progress' if r['polls']<4 else 'completed'
            return self.out(200,json.dumps({"id":rid,"status":st,"conclusion":(None if st!='completed' else 'failure' if r['fail'] else 'success'),"run_started_at":"2026-11-26T01:00:00Z","updated_at":"2026-11-26T01:06:10Z"}))
        if p.startswith(R+'/actions/artifacts/') and p.endswith('/zip'):
            if auth!='Bearer READ': return self.out(403,'{}')
            return self.out(302,b'',extra={'Location':'http://%s/blob/1'%self.headers.get('Host')})
        if p=='/blob/1':
            if auth: BODIES.append('AUTH-LEAK-TO-BLOB')
            return self.out(200,ZIP,'application/zip')
        return self.out(404,'{"message":"nf"}')
    do_GET=do_POST=do_PUT=do_DELETE=do_PATCH=do_ANY
http.server.ThreadingHTTPServer(('127.0.0.1',PORT),H).serve_forever()
