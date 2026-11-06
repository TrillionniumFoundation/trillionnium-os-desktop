import base64,binascii,hashlib,json,sys,zlib
WIRE_BYTES = 1105501
WIRE_SHA256 = 'bd702a652d6eb0e7754e27049ea18a9f1d5ba8216f1ec49468cd747641e5fc09'
STAGE_BYTES = 8389
STAGE_SHA256 = '5a108bcc09b17074d273d30ebc5a95c379e2bd2846e17ed276a5e283fe42e994'
INPUT_MAX_BYTES = 1048576
DECODED_MAX_BYTES = 2097152
ENCODED_BYTES = 316836
ENCODED_SHA256 = '5f7ff5109fe74c2e5d34bb1715b29bb7047f84ec4e814b0c544717f99633f374'
COMPRESSED_BYTES = 237625
COMPRESSED_SHA256 = '8a47101049b926dd1b130326e2ca52ba453a9f346974c061f74c984e179beb63'

def decode_exact_wire(encoded):
    if not (0 < ENCODED_BYTES <= INPUT_MAX_BYTES == 1048576 and
            0 < COMPRESSED_BYTES <= INPUT_MAX_BYTES and
            0 < WIRE_BYTES <= DECODED_MAX_BYTES == 2097152):
        raise RuntimeError('normal06 transport bounds invalid')
    if len(encoded) != ENCODED_BYTES or hashlib.sha256(encoded).hexdigest() != ENCODED_SHA256:
        raise RuntimeError('normal06 encoded input length or SHA changed')
    try:
        packed = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise RuntimeError('normal06 input is not strict base64') from error
    if base64.b64encode(packed) != encoded:
        raise RuntimeError('normal06 base64 is not canonical')
    if len(packed) != COMPRESSED_BYTES or hashlib.sha256(packed).hexdigest() != COMPRESSED_SHA256:
        raise RuntimeError('normal06 compressed stream length or SHA changed')
    decoder = zlib.decompressobj(wbits=zlib.MAX_WBITS)
    try:
        # Exactly one extra byte detects an expansion beyond the original size.
        # No unbounded flush is used; EOF and both tails must agree afterwards.
        raw = decoder.decompress(packed, WIRE_BYTES + 1)
    except zlib.error as error:
        raise RuntimeError('normal06 zlib stream invalid') from error
    if len(raw) != WIRE_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise RuntimeError('normal06 decoded length EOF or tail differs')
    if hashlib.sha256(raw).hexdigest() != WIRE_SHA256:
        raise RuntimeError('normal06 decoded original SHA changed')
    return raw

if sys.argv[1:] != ['--execute-once']:
    print(json.dumps({'state':'PLAN_ONLY','source_only':True,'submitted':False,'Main_actions':0,'Android_actions':0,'old_QA_epoch_invalid':True,'new_QA_epoch_qualified':False}))
    raise SystemExit(0)
if WIRE_BYTES is None or WIRE_SHA256 is None:
    raise RuntimeError('NORMAL06_EXACT_REQUEST_NOT_SEALED')
encoded=sys.stdin.buffer.read(ENCODED_BYTES+1)
raw=decode_exact_wire(encoded)
packet=json.loads(raw.decode('utf-8','strict'))
if set(packet)!={'schema','stage','files'} or type(packet['schema']) is not int or packet['schema']!=1:
    raise RuntimeError('normal framework source packet shape changed')
stage=packet['stage'].encode('utf-8')
if len(stage)!=STAGE_BYTES or hashlib.sha256(stage).hexdigest()!=STAGE_SHA256:
    raise RuntimeError('normal framework stage source changed')
scope={'__name__':'frozen_normal_framework_stage','__file__':'<frozen-normal-framework-stage>'}
exec(compile(stage,'stage.py','exec'),scope,scope)
scope['main'](packet['files'])
