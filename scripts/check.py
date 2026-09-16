#!/usr/bin/env python3
"""One entry point; no production URL, credentials, Docker startup or network install."""
import argparse, datetime, hashlib, json, os, shutil, socket, secrets, signal, subprocess, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def fingerprint():
    files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    return hashlib.sha256(b''.join(n.encode()+hashlib.sha256((ROOT/n).read_bytes()).digest() for n in sorted(files) if n and (ROOT/n).is_file() and not n.startswith(('vendor/','licenses/')))).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['check','quick','release'],nargs='?',default='check')
    p.add_argument('--feature',action='append',default=[],help='Feature ID from tests/feature_matrix.json; repeatable')
    p.add_argument('--list',action='store_true',help='List feature IDs and exit')
    p.add_argument('--output',type=Path,default=ROOT/'test-results/latest')
    p.add_argument('--corpus',type=Path,help='External sealed corpus directory, mandatory for release')
    a=p.parse_args();matrix=json.loads((ROOT/'tests/feature_matrix.json').read_text())
    if a.list:
        for f in matrix['features']:print(f['id']+': '+f['purpose'])
        return 0
    selected=[f for f in matrix['features'] if not a.feature or f['id'] in a.feature]
    unknown=set(a.feature)-{f['id'] for f in selected}
    if unknown:p.error('Unknown features: '+', '.join(sorted(unknown)))
    if a.mode=='release' and (a.feature or not a.corpus):p.error('release requires --corpus and cannot be narrowed by --feature')
    node=shutil.which('node')
    if not node:p.error('Node.js 22.12+ is required on PATH')
    if not (ROOT/'frontend/node_modules/typescript/bin/tsc').exists():p.error('Install locked frontend dependencies first; see docs/TESTING.md')
    output=a.output.resolve()/datetime.datetime.now().strftime('%Y%m%dT%H%M%S-%f');output.mkdir(parents=True,exist_ok=False)
    before=fingerprint();results=[];started=time.time()
    with tempfile.TemporaryDirectory(prefix='fgt-suite-') as folder:
        sandbox=Path(folder);(sandbox/'test-only').write_text(secrets.token_hex(24));env=os.environ.copy()
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env['SUITE_PORT']=str(port)
        if not env.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'):
            bundled=subprocess.run([node,'-e',"console.log(require('playwright').chromium.executablePath())"],cwd=ROOT/'frontend',capture_output=True,text=True)
            if bundled.returncode==0 and not Path(bundled.stdout.strip()).is_file():
                candidates=[shutil.which('chromium'),shutil.which('chromium-browser'),shutil.which('google-chrome')]
                if sys.platform=='darwin':candidates.append('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
                installed=next((c for c in candidates if c and Path(c).is_file()),None)
                if installed:env['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH']=installed
        for key in list(env):
            if key.startswith(('LEGACY_','RUN_LEGACY','SMTP_','SELENIUM_','CADDY_','PDF_RUNNER','RUNNER_')):env.pop(key,None)
        env.update(DB_PATH=str(sandbox/'unit.db'),UPLOADS_DIR=str(sandbox/'uploads'),ADMIN_STATE_DIR=str(sandbox/'admin'),APP_ORIGIN='http://testserver',APP_EDITION='private',TEAM_AUTH_ENABLED='false',ENABLE_SCRAPING='false',SUITE_SANDBOX=str(sandbox),SUITE_RESULTS=str(output),SUITE_EDITION=(ROOT/'EDITION').read_text().strip(),PYTHON_BINARY=sys.executable,NODE_BINARY=node,PYTHONDONTWRITEBYTECODE='1',RUN_PACK_CORPUS='0')
        def run(name,command,cwd=ROOT,timeout=1800):
            print('RUN '+name,flush=True);begin=time.time();log=output/(name+'.log')
            try:
                with log.open('w') as stream:
                    process=subprocess.Popen(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                    try:status=process.wait(timeout=timeout)
                    except (subprocess.TimeoutExpired,KeyboardInterrupt):
                        os.killpg(process.pid,signal.SIGTERM)
                        try:process.wait(timeout=5)
                        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                        status=124
            except OSError as error:
                log.write_text(str(error));status=127
            results.append(dict(stage=name,status='passed' if status==0 else 'failed',exit_code=status,seconds=round(time.time()-begin,2),log=str(log)))
            print(('PASS ' if status==0 else 'FAIL ')+name,flush=True)
            if status:print('\n'.join(log.read_text(errors='replace').splitlines()[-25:]),flush=True)
            return status==0
        # Fail closed on coverage drift before running selected tests.
        run('coverage-map',[sys.executable,'-m','pytest','tests/test_suite_contract.py','-q','--junitxml='+str(output/'coverage.xml')])
        front=run('typecheck',[node,'node_modules/typescript/bin/tsc','--noEmit'],ROOT/'frontend')
        if front:
            run('frontend-contracts',[node,'frontend/tests/run-content-parity.cjs'])
            front=run('build',[node,'node_modules/vite/bin/vite.js','build'],ROOT/'frontend')
            if front:front=run('api-renderer-build',[node,'scripts/build-api.cjs'])
        modules=sorted({path for f in selected for path in f['backend']})
        if not a.feature:modules=sorted(str(p.relative_to(ROOT)) for p in (ROOT/'tests').glob('test_*.py') if p.name not in matrix['separate'])
        if front:run('backend',[sys.executable,'-m','pytest',*modules,'-q','--tb=short','-o','faulthandler_timeout=60','--disable-warnings','-rs','--junitxml='+str(output/'backend.xml')])
        browser_ids={'navigation','release_selection','report_content','archives','progress','config_analysis','authentication','feature_gates','backups','certificates','event_logs','processing_settings','product_packs','workspaces','team_accounts','custom_roles','support','syslog','email','api_documentation','reviews','pdf_import','security','exports','consolidation'}
        if env['SUITE_EDITION']=='public':browser_ids-={'authentication','feature_gates','processing_settings','product_packs','workspaces','team_accounts','custom_roles','support','syslog','email'}
        browser_selected=not a.feature or bool(set(a.feature)&browser_ids)
        if a.mode!='quick' and front and browser_selected:
            args=[node,'node_modules/@playwright/test/cli.js','test','--config=playwright.config.cjs']
            if a.feature:args+=['--grep','|'.join('@feature:'+x+'(?: |$)' for x in a.feature)]
            run('browser',args,ROOT/'frontend')
        if a.mode=='release':
            run('packaging',[sys.executable,'-m','pytest','tests/test_release_packaging.py','-q','--junitxml='+str(output/'packaging.xml')])
            run('corpus',[sys.executable,'scripts/check_corpus.py',str(a.corpus.resolve()),'--output',str(output/'corpus.json')],timeout=7200)
            run('vendor',[sys.executable,'scripts/verify_vendor.py'])
        if not front:results.append(dict(stage='dependent-checks',status='blocked',exit_code=1,log='Backend/browser checks require a successful typecheck and build.'))
        stable=before==fingerprint()
        if not stable:results.append(dict(stage='source-stability',status='failed',exit_code=1,log='Source changed during the run; rerun the affected suite.'))
        status='passed' if all(r['status']=='passed' for r in results) else 'failed'
        import xml.etree.ElementTree as ET
        counts={}
        for name in ('backend','browser','coverage','packaging','product-pack-corpus'):
            report=output/(name+'.xml')
            if report.exists():
                suites=list(ET.parse(report).getroot().iter('testsuite'))
                counts[name]={key:sum(int(s.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
                counts[name]['skip_reasons']=sorted({sk.get('message','') for sk in ET.parse(report).getroot().iter('skipped')})
        summary=dict(test_counts=counts,browser_executable=env.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH','Playwright bundled Chromium'),status=status,mode=a.mode,features=a.feature or 'all',edition=env['SUITE_EDITION'],seconds=round(time.time()-started,2),source_fingerprint=before,source_unchanged=stable,stages=results,omitted=['browser'] if a.mode=='quick' or not browser_selected else [],release_checks_included=a.mode=='release')
        (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        (output/'SUMMARY.md').write_text('# Regression suite: '+status.upper()+'\n\n'+f"Mode: {a.mode}. Source unchanged: {stable}.\n\n"+'\n'.join(f"- {r['status'].upper()}: {r['stage']} — {r.get('seconds','?')}s; {r['log']}" for r in results)+'\n\nQuick mode omits browsers. Check mode omits packaging, private real-document corpus, and container deployment checks. See docs/TESTING.md.\n')
        (a.output.resolve()/'LATEST').write_text(str(output)+'\n')
        print('RESULT '+status.upper()+' — '+str(output/'SUMMARY.md'),flush=True)
        return 0 if status=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
