import json,secrets,sys
profile='p4-owner20-normal-20261106-02'
excluded={'eae6a2c3c00117d2a6a0f0f08949342de6a14cf8c2dbf695071e7a96b494661c','fcbc3154686575b1ace8760ab4bdabc7ef619026560a9a007388a86e31e6d873'}
nonce=secrets.token_hex(32)
if len(nonce)!=64 or nonce in excluded or any(c not in '0123456789abcdef' for c in nonce): raise RuntimeError('fresh exact owner02 nonce rejected; no redraw')
print(json.dumps({'schema':1,'profile':profile,'purpose':'fresh Owner20 normal02 attempt; no runtime action','nonce':nonce,'generator':'secrets.token_hex(32)','count':1,'excluded_known_prior_attempt_and_generation':sorted(excluded),'no_redraw':True,'Main_actions':0,'Android_actions':0},sort_keys=True),flush=True)
