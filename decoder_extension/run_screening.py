#!/usr/bin/env python3
"""Run the frozen Gate 2C comparison; this is a long, 12,960-invocation job."""
from pathlib import Path
import argparse, os, sys, json, hashlib, subprocess, time, traceback, threading, concurrent.futures
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parser_v2 import parse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--manifest', required=True, type=Path, help='manifest from generate_screening_inputs.py')
parser.add_argument('--production', required=True, type=Path, help='executable byte-identical WSJT-X 3.0.2 production wsprd')
parser.add_argument('--decoder-dir', required=True, type=Path, help='directory of binaries built with build.sh')
parser.add_argument('--output', required=True, type=Path, help='new output directory; must not already exist')
parser.add_argument('--check-only', action='store_true', help='verify inputs and executables without decoding or writing outputs')
args=parser.parse_args()
rows=[json.loads(x) for x in args.manifest.read_text().splitlines()]
if len(rows)!=1080 or len({r['key'] for r in rows})!=1080:
 raise SystemExit('manifest must contain the 1080 unique frozen inputs')
for r in rows:
 if hashlib.sha256(Path(r['file']).read_bytes()).hexdigest()!=r['sha256']:
  raise SystemExit('input hash mismatch: '+r['key'])
refs={'A0':args.production.resolve(),'B2':(args.decoder_dir/'wsprd-b2').resolve(),'B3':(args.decoder_dir/'wsprd-b3').resolve()}
budget={a:(args.decoder_dir/('wsprd-'+a.lower()+'-budget')).resolve() for a in refs}
if hashlib.sha256(refs['A0'].read_bytes()).hexdigest()!='9e3c2fc14f63c4b4c4e9fcc33b386cd22daf8fe76ce724c5e37f07875e9a3dd9':
 raise SystemExit('production binary hash mismatch')
for f in list(refs.values())+list(budget.values()):
 if not f.is_file() or not os.access(f,os.X_OK): raise SystemExit('not executable: '+str(f))
if args.check_only:
 print('PASS: 1080 input hashes, production hash, and six executable paths');sys.exit(0)
P=args.output.resolve()
P.mkdir(parents=True,exist_ok=False)
env=os.environ.copy()
for k in list(env):
 if k.startswith(('WSPR_ORACLE','WSPR_FACTORIAL','WSPR_TRUTH','WSPR_2B','WSPR_2C','WSPR_DIAG')):del env[k]
env['WSPR_2B_ENABLE']='1'
base=P/'runs';base.mkdir();stop=threading.Event();started=time.monotonic()
def process(r):
 recs=[];src=Path(r['file'])
 if hashlib.sha256(src.read_bytes()).hexdigest()!=r['sha256']:raise RuntimeError('input hash mismatch '+r['key'])
 root=base/r['key'];root.mkdir();natural={}
 for a in ('A0','B2','B3'):
  for mode in ('natural','generous','low','medium'):
   if stop.is_set():return recs
   w=root/(a+'_'+mode);w.mkdir();e=env.copy();binary=refs[a] if mode=='natural' else budget[a]
   if not(a=='A0' and mode=='natural'):e['WSPR_DIAG_FILE']=str(w/'trace.jsonl')
   if mode!='natural':e.update(WSPR_2C_ITER_LIMIT={'generous':'0','low':'40000000','medium':'100000000'}[mode],WSPR_2C_COARSE_LIMIT='0' if mode=='generous' else '100000',WSPR_2C_SYNC_LIMIT='0' if mode=='generous' else '10000',WSPR_2C_DEMOD_LIMIT='0' if mode=='generous' else '1000')
   cmd=[str(binary),'-H','-a',str(w),str(src)];t=time.monotonic();timeout=False
   try:
    q=subprocess.run(cmd,cwd=w,env=e,capture_output=True,timeout=120);stdout=q.stdout;stderr=q.stderr;code=q.returncode
   except subprocess.TimeoutExpired as ex:timeout=True;stdout=ex.stdout or b'';stderr=ex.stderr or b'';code=None
   wall=time.monotonic()-t;(w/'stdout.txt').write_bytes(stdout);(w/'stderr.txt').write_bytes(stderr)
   result={'key':r['key'],'kind':r['kind'],'input_sha256':r['sha256'],'arm':a,'mode':mode,'command':cmd,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'wall_seconds':wall,'timeout':timeout,'exit_status':code,'output_dir':str(w)}
   if timeout:result.update(outcome='timeout',parse_status='timeout',decoded_messages=[],budget_exhausted=None,cpu_seconds=None)
   else:
    expected_message=r.get('message',r.get('messages',[''])[0]);pr=parse(stdout.decode(),code,expected_message,stderr.decode());result.update(pr)
    if pr['parse_status']!='ok':(w/'record.json').write_text(json.dumps(result,indent=2));raise RuntimeError('invalid decoder output '+str((r['key'],a,mode,pr)))
    events=[json.loads(s,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v))) for s in (w/'trace.jsonl').read_text().splitlines()] if (w/'trace.jsonl').exists() else []
    if events and events[-1]['event']!='runtime':raise RuntimeError('incomplete trace '+str((r['key'],a,mode)))
    bt=[x for x in events if x['event']=='budget'];de=[x for x in events if x['event']=='decoder'];sets=[x for x in events if x['event']=='candidate_set'];grid=[x for x in events if x['event']=='grid_attempt'];scores=[x for x in events if x['event']=='grid_score'];vals=[x for x in events if x['event']=='validation']
    if mode!='natural' and len(bt)!=1:raise RuntimeError('missing budget trace '+str((r['key'],a,mode)))
    bm=bt[0] if bt else None
    if bm and (bm['fano_calls']!=len(de) or (mode=='low' and bm['fano_iterations']>40000000) or (mode=='medium' and bm['fano_iterations']>100000000)):raise RuntimeError('budget counter inconsistency')
    timer=(w/'wspr_timer.out').read_text().splitlines()[0].split();assert len(timer)==8
    result.update(cpu_seconds=events[-1]['cpu_seconds'] if events else float(timer[-1]),budget_exhausted=bool(bm['hit']) if bm else False,budget_kind=bm['kind'] if bm else None,fano_calls=bm['fano_calls'] if bm else (len(de) if events else None),fano_iterations=bm['fano_iterations'] if bm else (sum(x['cycles']-(2 if x['return_code']==-1 else 1) for x in de) if events else None),coarse_evaluations=bm['coarse_evaluations'] if bm else (sum(x['count']*160*(2*x['maxdrift']+1) for x in sets) if events else None),sync_calls=bm['sync_calls'] if bm else None,demod_calls=bm['demod_calls'] if bm else (sum(x['event']=='demod' for x in events) if events else None),grid_attempts=len(grid) if events else None,grid_score_evaluations=len(scores) if events else None,third_pass_candidate_ranks=len({x['rank0'] for x in events if x['event']=='demod' and x['pass']==3}) if events else None,validation_events=vals)
    if mode=='natural':natural[a]=w
    if mode=='generous' and a in natural:
     if bm['hit']:raise RuntimeError('generous budget exhausted '+str((r['key'],a,bm)))
     for name in ('stdout.txt','stderr.txt','ALL_WSPR.TXT','wspr_spots.txt'):
      if (w/name).read_bytes()!=(natural[a]/name).read_bytes():raise RuntimeError('generous mismatch '+str((r['key'],a,name)))
     result['matches_natural']=True
   (w/'record.json').write_text(json.dumps(result,indent=2)+'\n');recs.append(result)
 return recs
try:
 with (P/'trials.jsonl').open('x') as out:
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
   pending={pool.submit(process,r):r for r in rows}
   done=0
   for f in concurrent.futures.as_completed(pending):
    try:group=f.result()
    except BaseException:
     stop.set();[x.cancel() for x in pending];raise
    for item in group:out.write(json.dumps(item)+'\n')
    out.flush();done+=1
    if done%50==0:print('completed inputs',done,'/1080 wall',round(time.monotonic()-started,1),flush=True)
 assert done==1080
 (P/'comparison_PASS.json').write_text(json.dumps({'status':'PASS','inputs':done,'expected_invocations':12960,'wall_seconds':time.monotonic()-started},indent=2));print('COMPARISON PASS',done,flush=True)
except BaseException:
 stop.set();(P/'STOP_comparison.txt').write_text(traceback.format_exc());raise
