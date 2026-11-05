"""Independent formula prediction; no Gallery source or device state is modified."""
from pathlib import Path
from PIL import Image
import hashlib,json,types

ROOT=Path('/workspace/scratch/4c1c408226df')
GALLERY=ROOT/'gallery-video08'
HERE=Path(__file__).resolve().parent
COLORS=((255,59,48),(52,199,89),(0,122,255),(255,204,0))

def decode_170m(e):
    return e/4.5 if e<0.081 else ((e+0.099)/1.099)**(1/0.45)

def encode_srgb(linear):
    return 12.92*linear if linear<0.0031308 else 1.055*linear**(1/2.4)-0.055

def channel(code):return round(255*encode_srgb(decode_170m(code/255)))

PALETTE=tuple(tuple(channel(c) for c in pixel) for pixel in COLORS)
assert PALETTE==((255,74,64),(68,205,103),(0,134,255),(255,209,0))

def loaded(source,name):
    module=types.ModuleType(name);module.__file__=str(source)
    exec(compile(source.read_bytes(),str(source),'exec'),module.__dict__)
    return module

original=loaded(GALLERY/'verify_pattern.py','original_pattern')
video_pattern=loaded(GALLERY/'verify_pattern.py','isolated_video_pattern')
video_pattern.COLORS=PALETTE
video=types.ModuleType('isolated_video_verifier')
video.verify_pattern=video_pattern.verify_pattern
text=(GALLERY/'verify_video.py').read_text().replace('from verify_pattern import verify_pattern\n','')
exec(compile(text,'unchanged_video_methods','exec'),video.__dict__)
fixture=loaded(GALLERY/'make_owned_video.py','source_fixture')

def canvas(source,size=(1170,878)):
    out=Image.new('RGB',(1200,1520),(18,18,18))
    out.paste(source.resize(size),(15,321));return out

def synthetic(second,colors=COLORS,transfer=True):
    saved=fixture.COLORS
    try:fixture.COLORS=colors;raw=fixture.frame(second)
    finally:fixture.COLORS=saved
    image=Image.frombytes('RGB',(640,480),raw)
    return image.point([channel(i) for i in range(256)]*3) if transfer else image

checks=[]
def rejects(name,fn):
    try:fn()
    except RuntimeError as exc:checks.append({'case':name,'rejected':True,'reason':str(exc)});return
    raise AssertionError('Unexpected acceptance: '+name)

image_path=GALLERY/'owned-video-first-frame01.png'
assert hashlib.sha256(image_path.read_bytes()).hexdigest()=='7ef9d6c59c8bed56fdb6c9b0e68d14f1970468f88506c22ea867120423eebd1f'
actual=Image.open(image_path).convert('RGB')
rejects('original_png_palette_rejects_real_video_frame',lambda:original.verify_pattern(actual))
actual_proof=video.verify_video_frame(actual)
checks.append({'case':'standard_prediction_accepts_real_frame_with_unchanged_geometry_and_timecode',
    'passed':True,'visual_second_code':actual_proof['visual_second_code']})
for second in (0,1,17,59):
    proof=video.verify_video_frame(canvas(synthetic(second)))
    assert proof['visual_second_code']==second
    checks.append({'case':'standard_transfer_synthetic_second_'+str(second),'passed':True})
rejects('bypassed_video_transfer_wrong_palette',lambda:video.verify_video_frame(canvas(synthetic(17,transfer=False))))
rejects('wrong_quadrant_order',lambda:video.verify_video_frame(canvas(synthetic(17,colors=(COLORS[1],COLORS[0],COLORS[2],COLORS[3])))))
rejects('thumbnail_still_rejected',lambda:video.verify_video_frame(canvas(synthetic(17),size=(160,120))))
corrupt=synthetic(17)
for y in range(235,245):
    for x in range(100,132):corrupt.putpixel((x,y),(127,127,127))
rejects('timecode_nonbinary_still_rejected',lambda:video.verify_video_frame(canvas(corrupt)))
rejects('still_pixels_are_not_motion',lambda:video.verify_advancing({'visual_second_code':17},{'visual_second_code':17},4.0))
assert original.verify_pattern(canvas(synthetic(17,transfer=False)))['full_pattern_verified']
checks.append({'case':'original_png_palette_unchanged','passed':True})
observed=((255,74,63),(67,205,102),(0,134,253),(255,209,0))
result={'schema':'gallery-video-standard-transfer-independent-review-v1',
    'fixed_official_source':'https://android.googlesource.com/platform/frameworks/native/+/db4192ada9dee591ec897a51c07c489c84c860c1/libs/nativewindow/include/android/data_space.h',
    'official_blob':'d4278bedf3e5745105197386a242cd6fd1f1b4bf',
    'formula':'round(255 * sRGB_OETF(SMPTE170M_inverse_OETF(source_channel / 255)))',
    'source_palette':COLORS,'standard_predicted_palette':PALETTE,'observed_palette':observed,
    'observed_minus_standard':[[a-b for a,b in zip(o,p)] for o,p in zip(observed,PALETTE)],
    'maximum_absolute_channel_residual':max(abs(a-b) for o,p in zip(observed,PALETTE) for a,b in zip(o,p)),
    'tolerance_unchanged':6,'palette_fitted_to_screenshot':False,
    'actual_png_sha256':hashlib.sha256(image_path.read_bytes()).hexdigest(),
    'actual_frame_proof':actual_proof,'local_checks':checks,
    'source_files_sha256':{n:hashlib.sha256((GALLERY/n).read_bytes()).hexdigest() for n in
        ('verify_pattern.py','verify_video.py','make_owned_video.py','video-provenance.json')},
    'limits':['The standard transfer predicts all four observed colors within two 8-bit codes, but the actual Main compositor transfer implementation has not been bound to this upstream header.',
        'Accept this as a video-only fixture recognition model. It is not a color-fidelity qualification or evidence that every video uses this transfer.',
        'Retain the original PNG palette. Keep all current geometry, occupancy, aspect, timecode, elapsed motion, pause and thumbnail conditions.',
        'The original flow01 failure remains unchanged; this offline single-frame review is not a full playback gate.'],
    'device_actions':0,'root_source_files_modified':False,'playback_business_gate_passed':False}
out=HERE/'REVIEW.json'
out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'checks':len(checks),'predicted_palette':PALETTE,'max_residual':result['maximum_absolute_channel_residual'],
    'actual_second':actual_proof['visual_second_code'],'result_sha256':hashlib.sha256(out.read_bytes()).hexdigest()}))
