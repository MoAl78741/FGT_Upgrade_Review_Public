#!/usr/bin/env python3
"""Replay a sealed external FortiOS corpus; never generate or accept new goldens here."""
import argparse,hashlib,json,os,socket,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def changes(a,b,path='$'):
    if type(a)!=type(b):return [path]
    if isinstance(a,dict):
        return [p for k in sorted(a.keys()|b.keys()) for p in ([path+'.'+k] if k not in a or k not in b else changes(a[k],b[k],path+'.'+k))]
    if isinstance(a,list):
        if len(a)!=len(b):return [path+'.length']
        return [p for i,(x,y) in enumerate(zip(a,b)) for p in changes(x,y,f'{path}[{i}]')]
    return [] if a==b else [path]

def sealed(root,item):
    path=(root/item['path']).resolve()
    if not path.is_relative_to(root):raise ValueError('Corpus paths must stay inside the bundle')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Corpus seal mismatch: '+item['path'])
    return path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('corpus',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=a.corpus.resolve();manifest=json.loads((root/'manifest.json').read_text())
    if manifest.get('schema')!=1:raise ValueError('Unsupported corpus schema')
    cases=manifest['cases'];ids=[c['id'] for c in cases]
    if not cases or len(ids)!=len(set(ids)):raise ValueError('Corpus cases must be nonempty and uniquely named')
    if not {'6.4','7.0','7.2','7.4','7.6'}<={c['family'] for c in cases}:raise ValueError('Release corpus must cover FortiOS 6.4, 7.0, 7.2, 7.4 and 7.6')
    def forbidden(*args,**kwargs):raise RuntimeError('Network forbidden during corpus replay')
    socket.socket.connect=forbidden;socket.socket.connect_ex=forbidden;socket.socket.sendto=forbidden;socket.getaddrinfo=forbidden
    from backend.pdf_parser import parse_pdf
    from backend.pdf_document import open_document
    results=[]
    for case in cases:
        start=time.monotonic();record={'id':case['id'],'status':'failed'}
        try:
            pdf=sealed(root,case['pdf']);expected=json.loads(sealed(root,case['golden']).read_text())
            if expected['sha256']!=case['pdf']['sha256']:raise ValueError('Golden describes a different source PDF')
            with open_document(pdf) as document:pages=len(document)
            actual=json.loads(json.dumps(parse_pdf(pdf)));delta=changes(expected['result'],actual)
            if pages!=expected['page_count']:delta.append('$.page_count')
            # The parser result comparison includes every original source string and field.
            record.update(status='passed' if not delta else 'failed',pages=pages,difference_count=len(delta),difference_paths=delta[:30])
        except Exception as e:record['error']=str(e)
        record['seconds']=round(time.monotonic()-start,2);results.append(record);print(json.dumps(record),flush=True)
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(results,indent=2)+'\n')
    return int(any(r['status']!='passed' for r in results))
if __name__=='__main__':raise SystemExit(main())
