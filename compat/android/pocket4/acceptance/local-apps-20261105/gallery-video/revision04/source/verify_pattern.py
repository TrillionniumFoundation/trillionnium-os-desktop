"""Verify the four known quadrants occupy a full Gallery image, not a thumbnail."""
import math

# Video-only reference for the fixed, untagged YCbCr fixture.
# Android's documented default video transfer is SMPTE 170M; an sRGB
# capture therefore uses sRGB_OETF(SMPTE170M_inverse_OETF(encoded_value)).
# This reference is derived from the standard, never fitted to a screenshot.
# https://android.googlesource.com/platform/frameworks/native/+/db4192ada9dee591ec897a51c07c489c84c860c1/libs/nativewindow/include/android/data_space.h
# It recognizes this fixture; it does not qualify color fidelity or bind the
# installed compositor to that upstream implementation.
SOURCE_COLORS=((255,59,48),(52,199,89),(0,122,255),(255,204,0))
def video_channel_in_srgb(value):
    encoded=value/255.0
    linear=encoded/4.5 if encoded<0.081 else ((encoded+0.099)/1.099)**(1/0.45)
    srgb=12.92*linear if linear<0.0031308 else 1.055*linear**(1/2.4)-0.055
    return round(255*srgb)
COLORS=tuple(tuple(video_channel_in_srgb(c) for c in rgb) for rgb in SOURCE_COLORS)

def verify_pattern(image):
    def need(value,reason):
        if not value:raise RuntimeError(reason)
    need(image.mode=='RGB' and min(image.size)>=120,'SCOPED_IMAGE_SIZE')
    factor=max(1,math.ceil(max(image.size)/360))
    small=image.resize((image.width//factor,image.height//factor),resample=0)
    groups=[[] for _ in COLORS]
    for i,pixel in enumerate(small.getdata()):
        for c,target in enumerate(COLORS):
            if all(abs(pixel[j]-target[j])<=6 for j in range(3)):
                groups[c].append((i%small.width,i//small.width));break
    need(all(len(g)>=40 for g in groups),'FOUR_OWNED_QUADRANTS_REQUIRED')
    boxes=[]
    for points in groups:
        l=min(x for x,y in points);r=max(x for x,y in points)+1
        t=min(y for x,y in points);b=max(y for x,y in points)+1
        need(len(points)/((r-l)*(b-t))>=0.94,'QUADRANT_NOT_A_SOLID_RECTANGLE')
        boxes.append((l,t,r,b))
    red,green,blue,yellow=boxes
    need(red[2]<=green[0] and blue[2]<=yellow[0] and red[3]<=blue[1]
        and green[3]<=yellow[1],'OWNED_QUADRANT_ORDER_CHANGED')
    need(all(abs(a-b)<=2 for a,b in ((red[0],blue[0]),(green[0],yellow[0]),
        (red[2],blue[2]),(green[2],yellow[2]),(red[1],green[1]),(blue[1],yellow[1]),
        (red[3],green[3]),(blue[3],yellow[3]))),'QUADRANT_GRID_CHANGED')
    l=min(b[0] for b in boxes);t=min(b[1] for b in boxes)
    r=max(b[2] for b in boxes);b=max(b[3] for b in boxes);width=r-l;height=b-t
    need(abs(width/height-640/480)<0.065,'OWNED_IMAGE_ASPECT_CHANGED')
    need(width>=min(small.width*.70,small.height*.90)
        and width*height>=small.width*small.height*.23,'THUMBNAIL_NOT_FULL_IMAGE')
    need(sum(map(len,groups))/(width*height)>.84,'OWNED_IMAGE_INTERIOR_OCCLUDED')
    return {'full_pattern_verified':True,'scope_size':list(image.size),'sample_size':list(small.size),
        'color_order':['red','green','blue','yellow'],'quadrant_counts':list(map(len,groups)),
        'sample_pattern_bounds':[l,t,r,b],'sample_quadrant_bounds':[list(x) for x in boxes],
        'scope_fraction':width*height/(small.width*small.height),'source_aspect':[640,480],
        'color_tolerance':6,'thumbnail_excluded':True}
