#!/usr/bin/env python3
"""Reparse and verify every completed fresh Gate 2C invocation."""
from pathlib import Path
import argparse,json,hashlib,sys,collections
sys.path.insert(0,str(Path(__file__).resolve().parent))
from parser_v2 import parse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--manifest',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args();P=args.output.resolve();I=args.manifest.resolve().parent
assert json.loads((P/'comparison_PASS.json').read_text())['status']=='PASS';manifest={r['key']:r for r in map(json.loads,args.manifest.read_text().splitlines())};rows=[json.loads(x) for x in (P/'trials.jsonl').read_text().splitlines()];assert len(rows)==12960 and len({(r['key'],r['arm'],r['mode']) for r in rows})==12960;idx={(r['key'],r['arm'],r['mode']):r for r in rows};counts=collections.Counter();timeouts=[]
for key,r in manifest.items():
 f=Path(r['file']);assert hashlib.sha256(f.read_bytes()).hexdigest()==r['sha256']
 for arm in ('A0','B2','B3'):
  natural=idx[(key,arm,'natural')];generous=idx[(key,arm,'generous')]
  for mode in ('natural','generous','low','medium'):
   t=idx[(key,arm,mode)];counts[arm+'_'+mode]+=1;assert t['input_sha256']==r['sha256'];w=Path(t['output_dir']);assert json.loads((w/'record.json').read_text())==t;assert w.is_relative_to(P/'runs')
   if t['timeout']:timeouts.append((key,arm,mode));continue
   so=(w/'stdout.txt').read_text();se=(w/'stderr.txt').read_text();expect=r.get('message',r.get('messages',[''])[0]);v=parse(so,t['exit_status'],expect,se)
   assert all(v[x]==t[x] for x in ('decoded_messages','expected_message_present','unexpected_message_present','outcome','parse_status','finish_count'));assert v['parse_status']=='ok'
   if mode!='natural':
    ev=[json.loads(x,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x))) for x in (w/'trace.jsonl').read_text().splitlines()];b=next(e for e in ev if e['event']=='budget');assert b['fano_iterations']==t['fano_iterations'] and b['fano_calls']==t['fano_calls'] and bool(b['hit'])==t['budget_exhausted'];assert ev[-1]['event']=='runtime'
    if mode=='low':assert b['fano_iterations']<=40000000
    if mode=='medium':assert b['fano_iterations']<=100000000
    if b['hit'] and b['kind']==3:assert b['fano_iterations']==({'low':40000000,'medium':100000000}[mode])
  if not natural['timeout'] and not generous['timeout']:
   assert generous.get('matches_natural') is True
   a=Path(natural['output_dir']);b=Path(generous['output_dir'])
   for f in ('stdout.txt','stderr.txt','ALL_WSPR.TXT','wspr_spots.txt'):assert (a/f).read_bytes()==(b/f).read_bytes(),(key,arm,f)
(P/'independent_comparison_PASS.json').write_text(json.dumps({'status':'PASS','unique_inputs':1080,'invocations':len(rows),'counts':dict(counts),'timeouts':timeouts,'input_hashes':'PASS','output_reparse':'PASS','generous_vs_natural':'PASS for completed pairs','prior_archives':'not checked by this fresh-run verifier'},indent=2)+'\n');print('INDEPENDENT COMPARISON PASS',len(rows),'timeouts',len(timeouts))
