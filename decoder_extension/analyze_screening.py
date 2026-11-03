#!/usr/bin/env python3
"""Compute per-cell exploratory Gate 2C comparisons from verified results."""
from pathlib import Path
import argparse,json,csv,math,statistics
import numpy as np
from scipy.stats import beta
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--manifest',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args();P=args.output.resolve();I=args.manifest.resolve().parent
assert json.loads((P/'independent_comparison_PASS.json').read_text())['status']=='PASS'
manifest=[json.loads(x) for x in args.manifest.read_text().splitlines()];meta={r['key']:r for r in manifest};trials=[json.loads(x) for x in (P/'trials.jsonl').read_text().splitlines()];index={(x['key'],x['arm'],x['mode']):x for x in trials};assert len(index)==len(trials)==12960
arms=('A0','B2','B3');modes=('natural','low','medium');snrs=(-30.5,-31.0);drifts=(0.,.5,-.5,.75,-1.5);messages=('W1AW FN31 37','VK3ABC QF22 30')
def cp(k,n,alpha=.025):return (0. if not k else float(beta.ppf(alpha/2,k,n-k+1)),1. if k==n else float(beta.ppf(1-alpha/2,k+1,n-k)))
def pair_interval(g,l,n):
 a,b=cp(g,n);c,d=cp(l,n);return max(-1,a-d),min(1,b-c)
def wilson(k,n):
 if not n:return None,None
 z=1.959963984540054;q=k/n;den=1+z*z/n;mid=(q+z*z/(2*n))/den;h=z*math.sqrt(q*(1-q)/n+z*z/(4*n*n))/den;return mid-h,mid+h
def ok(x,msg):return msg in x['decoded_messages']
def cost_rows(keys,arm,mode):
 out=[]
 for k in keys:
  x=index[(k,arm,mode)];v=dict(x)
  if mode=='natural':
   g=index[(k,arm,'generous')]
   for c in ('fano_calls','fano_iterations','coarse_evaluations','sync_calls','demod_calls','grid_attempts','grid_score_evaluations','third_pass_candidate_ranks','validation_events'):
    if v.get(c) is None:v[c]=g.get(c)
  out.append(v)
 return out
def cost(rs):
 result={}
 for c in ('cpu_seconds','wall_seconds','fano_calls','fano_iterations','coarse_evaluations','sync_calls','demod_calls','grid_attempts','grid_score_evaluations','third_pass_candidate_ranks'):
  vals=[r[c] for r in rs if r.get(c) is not None]
  result[c+'_sum']=sum(vals) if vals else None
  for q in (50,90,95):result[c+'_p'+str(q)]=float(np.percentile(vals,q)) if vals else None
 result['budget_exhaustions']=sum(r.get('budget_exhausted') is True for r in rs);result['timeouts']=sum(r['timeout'] for r in rs);result['errors']=sum(r.get('parse_status') not in ('ok','timeout') for r in rs)
 result['validation_duplicates']=sum(sum(bool(e['duplicate']) for e in r.get('validation_events',[])) for r in rs)
 return result
signal=[]
for msg in messages:
 for snr in snrs:
  for d in drifts:
   keys=[r['key'] for r in manifest if r['kind']=='signal' and r['message']==msg and r['snr']==snr and r['drift']==d];assert len(keys)==40
   for mode in modes:
    for arm in arms:
     rs=cost_rows(keys,arm,mode);bas=cost_rows(keys,'A0',mode);n=len(keys);good=sum(ok(x,msg) for x in rs);wrong=sum(bool(x['decoded_messages']) and not ok(x,msg) for x in rs);unexpected=sum(any(m!=msg for m in x['decoded_messages']) for x in rs);no=sum(x['outcome']=='no_decode' for x in rs);g=sum(ok(x,msg) and not ok(y,msg) for x,y in zip(rs,bas));l=sum(not ok(x,msg) and ok(y,msg) for x,y in zip(rs,bas));lo,hi=wilson(good,n);dl,dh=pair_interval(g,l,n);dct={'message':msg,'snr':snr,'drift':d,'arm':arm,'mode':mode,'n':n,'correct':good,'wrong_only':wrong,'no_decode':no,'unexpected_trials':unexpected,'rate':good/n,'rate_low':lo,'rate_high':hi,'gain_vs_a0':g,'loss_vs_a0':l,'paired_difference':(g-l)/n,'paired_low':dl,'paired_high':dh,**cost(rs)};work=dct['fano_iterations_sum'];dct['correct_per_billion_fano_iterations']=good*1e9/work if work else None;signal.append(dct)
noise=[]
for snr in (*snrs,'combined'):
 keys=[r['key'] for r in manifest if r['kind']=='noise' and (snr=='combined' or r['snr_reference']==snr)];assert len(keys)==(200 if snr=='combined' else 100)
 for mode in modes:
  for arm in arms:
   rs=cost_rows(keys,arm,mode);n=len(rs);hits=sum(bool(x['decoded_messages']) for x in rs);lo,hi=wilson(hits,n);noise.append({'snr_reference':snr,'arm':arm,'mode':mode,'n':n,'false_detection_frames':hits,'false_messages':sum(len(x['decoded_messages']) for x in rs),'false_rate':hits/n,'wilson_low':lo,'wilson_high':hi,**cost(rs)})
multi=[]
for snr in snrs:
 for cond in (0,1):
  keys=[r['key'] for r in manifest if r['kind']=='multi' and r['snr']==snr and r['condition']==cond];assert len(keys)==20
  for mode in modes:
   for arm in arms:
    rs=cost_rows(keys,arm,mode);bas=cost_rows(keys,'A0',mode);correct=[sum(ok(x,msg) for x in rs) for msg in messages];unexpected=sum(any(m not in messages for m in x['decoded_messages']) for x in rs);dupes=sum(len(x['decoded_messages'])!=len(set(x['decoded_messages'])) for x in rs);row={'snr':snr,'condition':cond,'drift_pair':str([0,0] if cond==0 else [.75,-1.5]),'arm':arm,'mode':mode,'n':len(keys),'message1_correct':correct[0],'message2_correct':correct[1],'both_correct':sum(all(ok(x,m) for m in messages) for x in rs),'neither':sum(not any(ok(x,m) for m in messages) for x in rs),'unexpected_trials':unexpected,'duplicate_output_frames':dupes,**cost(rs)}
    for j,msg in enumerate(messages,1):
     row['message%d_gain_vs_a0'%j]=sum(ok(x,msg) and not ok(y,msg) for x,y in zip(rs,bas));row['message%d_loss_vs_a0'%j]=sum(not ok(x,msg) and ok(y,msg) for x,y in zip(rs,bas))
    multi.append(row)
def write(name,rows):
 with (P/name).open('x',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
write('signal_cells.csv',signal);write('null_cells.csv',noise);write('multi_cells.csv',multi)

ordering=[]
for msg in messages:
 for snr in snrs:
  for d in drifts:
   keys=[r['key'] for r in manifest if r['kind']=='signal' and r['message']==msg and r['snr']==snr and r['drift']==d]
   for mode in modes:
    b2=cost_rows(keys,'B2',mode);b3=cost_rows(keys,'B3',mode);g=sum(ok(x,msg) and not ok(y,msg) for x,y in zip(b2,b3));l=sum(not ok(x,msg) and ok(y,msg) for x,y in zip(b2,b3));dl,dh=pair_interval(g,l,len(keys));delta=[x['cpu_seconds']-y['cpu_seconds'] for x,y in zip(b2,b3) if x.get('cpu_seconds') is not None and y.get('cpu_seconds') is not None];fc=[x['fano_calls']-y['fano_calls'] for x,y in zip(b2,b3) if x.get('fano_calls') is not None and y.get('fano_calls') is not None]
    ordering.append({'message':msg,'snr':snr,'drift':d,'mode':mode,'n':len(keys),'b2_only_correct':g,'b3_only_correct':l,'b2_minus_b3_rate':(g-l)/len(keys),'paired_low':dl,'paired_high':dh,'paired_cpu_seconds_difference_median':statistics.median(delta) if delta else None,'paired_fano_calls_difference_median':statistics.median(fc) if fc else None,'b2_less_cpu_count':sum(x<0 for x in delta),'b3_less_cpu_count':sum(x>0 for x in delta)})
write('ordering_cells.csv',ordering)

with (P/'paired_signal_trials.jsonl').open('x') as f:
 for r in manifest:
  if r['kind']=='signal':f.write(json.dumps({'key':r['key'],'message':r['message'],'snr':r['snr'],'drift':r['drift'],'seed':r['seed'],'outcomes':{a+'_'+m:ok(index[(r['key'],a,m)],r['message']) for a in arms for m in modes}})+'\n')
print('ANALYSIS PASS','signal cells',len(signal),'noise cells',len(noise),'multi cells',len(multi))
