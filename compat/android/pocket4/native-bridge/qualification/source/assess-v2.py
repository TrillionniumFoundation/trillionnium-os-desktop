"""Strict assessments of only nonce/PID/UID-attributed owned probe payloads."""
import struct
def tokens(line):
 pairs=[s.split('=',1) for s in line.split()]
 assert all(len(p)==2 for p in pairs)
 out=dict(pairs);assert len(out)==len(pairs);return out
def integer(row,key):return int(row[key],0)
def assess(version,payload,nonce,pid,uid,arm,mode='controls',expected_cpu_count=None):
 rows=[tokens(x) for x in payload]
 assert rows and all(r['run_id']==nonce for r in rows)
 if version!=4:assert all(int(r['pid'])==pid and int(r['uid'])==uid for r in rows)
 assert not any('exception' in r.get('phase','') for r in rows)
 phase=[r['phase'] for r in rows]
 if version==4:
  assert len(rows)==20 and phase[0]=='before-load' and phase[-1]=='complete'
  result=[r for r in rows if r['phase']=='native-result'];assert len(result)==9
  query={r['query']:r for r in result if 'query' in r};register={r['register']:r for r in result if 'register' in r}
  assert set(query)=={'AT_HWCAP','AT_HWCAP2','GETAUXVAL_ADDRESS','CPUINFO_OPENAT','CPUINFO_OPENAT2'}
  hwcap=int(query['AT_HWCAP']['value']);assert hwcap>0 and int(query['GETAUXVAL_ADDRESS']['value'])>0
  q=query['CPUINFO_OPENAT'];assert type(expected_cpu_count) is int and expected_cpu_count>0
  assert int(q['value'])>0 and int(q['count'])==expected_cpu_count and int(q['value'])>>32==expected_cpu_count and int(q['feature_mask_hex'],16)==hwcap and (int(q['value'])&0xffffffff)==hwcap and q['matches_actual_auxv']=='true'
  for name,val in {'PFR1':0,'PFR0':17,'ISAR0':0x211120,'ISAR1':0}.items():
   r=register[name];assert int(r['value'])==val and int(r['hex'],16)==val and r['match']=='true'
  assert rows[-1]['pass']=='true';return {'classification':'PASS_V4_MRS_CPUINFO','hwcap':hwcap,'openat2_observation':query['CPUINFO_OPENAT2']}
 if version in (5,6):
  cases=1 if version==5 else 16
  assert phase==['before-load']+['before-native','result','raw-siginfo']*cases+['complete']
  for c in range(cases):
   before,r,raw=rows[1+3*c:4+3*c]
   if version==6:assert int(before['case'])==int(r['case'])==int(raw['case'])==c
   for key,val in {'status':0,'install_rc':0,'restore_rc':0,'count':1,'handler_signo':4,'info_signo':4,'info_errno':0,'info_code':1,'resumed':1,'unexpected':0}.items():assert integer(r,key)==val,(version,c,key,r[key])
   fault=integer(r,'expected_pc');assert fault>0 and integer(r,'info_addr')==integer(r,'context_pc')==fault
   assert r['pass']=='true' and int(raw['bytes'])==128
   data=bytes.fromhex(raw['hex']);assert len(data)==128 and struct.unpack_from('<iii',data)==(4,0,1) and struct.unpack_from('<Q',data,16)[0]==fault
   if version==6:
    initial=c<<28;edited=(c^15)<<28;saved=integer(r,'saved_pstate')
    assert integer(r,'stored_status')==0 and integer(r,'initial')==initial and integer(r,'edited')==edited
    assert saved&0xf0000000==initial and integer(r,'written_pstate')==(saved&~0xf0000000)|edited and integer(r,'observed_nzcv')==edited
    for key in ('outside_preserved','gpr_x9_x10','sp','simd32','fpcr_fpsr','saved_record'):assert integer(r,key)==1
    assert integer(r,'native_case')==c
  assert rows[-1]['pass']=='true' and int(rows[-1]['cases'])==cases
  if version==6:assert int(rows[-1]['passed'])==16
  return {'classification':'PASS_V'+str(version)+'_ACTUAL_SIGNAL_RECORDS','cases':cases,'events':len(rows)}
 assert version==8 and all(r['mode']==mode for r in rows)
 expected_initial=1 if arm=='r14' else 0
 assert phase[:2]==['before-load','loaded'] and int(rows[1]['initial_alarm'])==expected_initial
 if mode=='default-alarm':
  assert phase[2]=='before-native' and int(rows[2]['case'])==5
  if arm=='r14':
   assert phase==['before-load','loaded','before-native','result','complete']
   r=rows[3];assert int(r['case'])==5 and int(r['returned'])==0 and int(r['f1'])==5 and int(r['f2'])==pid and int(r['f3'])==uid and int(r['f6'])==1 and int(r['f7'])==0
   return {'classification':'EXPECTED_R14_IGNORED_ALARM_RETURN','initial_alarm':1}
  assert len(rows)==3
  return {'classification':'DEFAULT_ALARM_ARMED_NO_RETURN','initial_alarm':0}
 assert phase==['before-load','loaded']+['before-native','result']*5+['complete']
 statuses=[]
 for c in range(5):
  before,r=rows[2+2*c:4+2*c];assert int(before['case'])==int(r['case'])==c
  f=[int(r['f'+str(i)]) for i in range(40)]
  assert f[:4]==[1,c,pid,uid] and int(r['returned'])==f[4]
  expected=32 if c<2 and arm!='r16' else 0
  assert f[4]==expected,(arm,c,f[4],expected);statuses.append(f[4])
  if c<4:
   base=f[6]+(4096 if c==3 else 0);count=1 if c==2 else 3;assert f[9]==count
   assert f[8]==(0 if c==3 else (1<<32)+8192 if c==1 else 8192)
   assert f[12]==0 and f[15]==0 and f[16]==0 and f[17]==0 and f[14]>0
   for i in range(count):
    a=18+7*i
    assert f[a]==base+(0 if c==2 else i*4096) and f[a+1]==base+(3 if c==2 else i+1)*4096
    off=0 if c==3 else f[8]+(i*4096 if arm=='r16' or c==2 else 0)
    assert f[a+2]==off and f[a+3]==(13 if c!=2 and i==1 else 9)
    if c==3:assert f[a+4:a+7]==[0,0,0]
    else:assert f[a+6]>0 and f[a+4:a+7]==f[22:25]
  else:
   assert f[7]==expected_initial and f[30]==expected_initial and f[9]==f[32]
   for i in (6,8,10,11,12,14,15,16,19,27,28,29,31):assert f[i]==0
   assert f[13]==f[18]==1 and f[20]==2 and f[17]&(1<<13)
   assert f[21:27]==[14,14,0,-6,pid,uid]
 assert int(rows[-1]['cases'])==5 and int(rows[-1]['own_status_zero'])==(1 if arm=='r16' else 0)
 return {'classification':'PASS_V8_MAPS_AND_SIGNAL_CONTROL' if arm=='r16' else 'EXPECTED_'+arm.upper()+'_MAPS_OFFSET_NEGATIVE_WITH_SIGNAL_CONTROL_PASS','map_statuses':statuses[:4],'signal_status':statuses[4],'initial_alarm':expected_initial}
