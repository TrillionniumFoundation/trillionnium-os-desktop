import base64,binascii,hashlib,json,sys,zlib
WIRE_BYTES = 1305032
WIRE_SHA256 = '600ddd2ad954a34e1fb2c5098901b13531c13b37f1c733f5421e4818b4a9d549'
STAGE_BYTES = 9801
STAGE_SHA256 = '4f5869fc262e128fb397177c641a73bea9fb17b0aebe8a69344add1e29019a4b'
INPUT_MAX_BYTES = 1048576
DECODED_MAX_BYTES = 2097152
ENCODED_BYTES = 353320
ENCODED_SHA256 = 'd94feeb040c858c67f579907bc188362db8d7b907567a2a773b1a458bbaa0c90'
COMPRESSED_BYTES = 264989
COMPRESSED_SHA256 = 'f62aa0491b72274ca2ff7735f0d14f390205f29a57a5489d006722575312a36d'

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
