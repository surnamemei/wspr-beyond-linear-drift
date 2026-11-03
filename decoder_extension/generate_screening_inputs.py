#!/usr/bin/env python3
"""Regenerate the frozen Gate 2C inputs in a new, empty directory.

This creates 1080 C2 files (~389 MB) but does not run any decoder.
"""
import argparse
import json
import math
import random
import hashlib
import struct
import pathlib
import sys
import traceback
import numpy as np
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wspr.encoder import encode_type1
from wspr.waveform import generate_complex_baseband
from impairments.frequency import wsprd_linear_drift_trajectory, embed_active_trajectory, apply_frequency_error
from impairments.noise import complex_noise_power_for_wspr_snr
header = struct.pack('<14sid', b'261103_0000.c2', 2, 10.1387)
drift_tags = ['z', 'p05', 'm05', 'p075', 'm15']

def frame(msg,d,freq=0.,delay=1.,phase=0.):
 wave=generate_complex_baseband(encode_type1(msg).channel_symbols,center_frequency_hz=freq,start_delay_s=delay,initial_phase_rad=phase);traj=embed_active_trajectory(len(wave.samples),wave.frame_start_sample,wsprd_linear_drift_trajectory(162,256,d));return np.asarray(apply_frequency_error(wave.samples,traj,375),dtype=np.complex128)
def noise(seed,snr):
 sig=math.sqrt(complex_noise_power_for_wspr_snr(1.,snr)/2.);r=random.Random(seed);return np.fromiter((complex(r.gauss(0,sig),r.gauss(0,sig)) for _ in range(45000)),np.complex128,count=45000)
def save(f,z):
 xy=np.empty((45000,2),dtype='<f4');xy[:,0]=z.real;xy[:,1]=-z.imag
 with f.open('xb') as h:h.write(header);h.write(xy.tobytes())
 return hashlib.sha256(f.read_bytes()).hexdigest()

def generate(P, policy):
 P = pathlib.Path(P).resolve()
 P.mkdir(parents=True, exist_ok=False)
 inputs=P/'inputs'; inputs.mkdir()
 msgs=policy['messages']; snrs=policy['snr_db_2500']; drifts=policy['signal_drifts_hz']
 try:
  clean={(mi,di):frame(msg,d) for mi,msg in enumerate(msgs) for di,d in enumerate(drifts)}
  multi={(ci,mi):frame(msg,policy['multi_spec']['drift_pairs'][ci][mi],policy['multi_spec']['center_hz'][mi],policy['multi_spec']['start_seconds'][mi],policy['multi_spec']['initial_phase_radians'][mi]) for ci in (0,1) for mi,msg in enumerate(msgs)}
  count=0
  with (P/'manifest.jsonl').open('x') as out:
   def save_row(key,z,row):
    nonlocal count
    folder=inputs/key;folder.mkdir();f=folder/'261103_0000.c2';row.update({'key':key,'file':str(f),'sha256':save(f,z)});out.write(json.dumps(row)+'\n');out.flush();count+=1
   for mi,msg in enumerate(msgs):
    for si,snr in enumerate(snrs):
     for ti in range(40):
      seed=3000000000+mi*100000+si*10000+ti;n=noise(seed,snr)
      for di,d in enumerate(drifts):save_row('sig_m%d_s%d_d%s_t%02d'%(mi,si,drift_tags[di],ti),clean[(mi,di)]+n,{'kind':'signal','message':msg,'message_index':mi,'snr':snr,'drift':d,'index':ti,'seed':seed})
     print('generated signal message',mi,'snr',snr,'count',count,flush=True)
   for si,snr in enumerate(snrs):
    for ti in range(100):
     seed=3100000000+si*10000+ti;save_row('null_s%d_t%03d'%(si,ti),noise(seed,snr),{'kind':'noise','snr_reference':snr,'index':ti,'seed':seed})
   print('generated null count',count,flush=True)
   for si,snr in enumerate(snrs):
    for ci in (0,1):
     for ti in range(20):
      seed=3200000000+si*10000+ci*1000+ti;z=multi[(ci,0)]+multi[(ci,1)]+noise(seed,snr);save_row('multi_s%d_c%d_t%02d'%(si,ci,ti),z,{'kind':'multi','messages':msgs,'snr':snr,'condition':ci,'drifts':policy['multi_spec']['drift_pairs'][ci],'index':ti,'seed':seed})
   print('generated complete',count,flush=True)
  rows=[json.loads(x) for x in (P/'manifest.jsonl').read_text().splitlines()];assert len(rows)==1080 and len({r['key'] for r in rows})==1080 and sum(r['kind']=='signal' for r in rows)==800 and sum(r['kind']=='noise' for r in rows)==200 and sum(r['kind']=='multi' for r in rows)==80
  assert len({r['sha256'] for r in rows})==1080
  for r in rows:
   b=pathlib.Path(r['file']).read_bytes();assert len(b)==360026 and b[:26]==header and hashlib.sha256(b).hexdigest()==r['sha256']
  # Check pairing independently against the frozen clean signal after float32 serialization.
  for mi in range(2):
   for si in range(2):
    for ti in range(40):
     q=[r for r in rows if r['kind']=='signal' and r['message_index']==mi and r['snr']==snrs[si] and r['index']==ti];assert len(q)==5 and len({r['seed'] for r in q})==1
     residual=[]
     for r in q:
      b=pathlib.Path(r['file']).read_bytes();v=np.frombuffer(b,dtype='<f4',offset=26).reshape(-1,2);z=v[:,0].astype(float)-1j*v[:,1].astype(float);residual.append(z-clean[(mi,drifts.index(r['drift']))])
     assert max(np.max(np.abs(x-residual[0])) for x in residual[1:])<1e-5
  seedsets=[{r['seed'] for r in rows if r['kind']==kind} for kind in ('signal','noise','multi')];assert len(seedsets[0])==160 and len(seedsets[1])==200 and len(seedsets[2])==80 and not any(seedsets[i]&seedsets[j] for i in range(3) for j in range(i+1,3))
  (P/'input_integrity_PASS.json').write_text(json.dumps({'status':'PASS','total':1080,'signal':800,'noise':200,'multi':80,'sha256_unique':1080,'paired_noise_checks':160,'seed_counts':[len(x) for x in seedsets],'manifest_sha256':hashlib.sha256((P/'manifest.jsonl').read_bytes()).hexdigest()},indent=2));print('INPUTS INTEGRITY PASS 1080',flush=True)
 except BaseException:
  (P/'STOP_inputs.txt').write_text(traceback.format_exc());raise

if __name__ == "__main__":
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("output", type=pathlib.Path, help="new output directory; must not already exist")
 args=parser.parse_args()
 policy=json.loads((ROOT/'decoder_extension/screening_protocol.json').read_text())
 generate(args.output, policy)
