"""Recognize this fixture's JPEG pixels; metadata and UI routing are separate gates.

The palette comes from the known generated JPEG before Gallery runs. It never
comes from a screenshot. The original PNG verifier remains unchanged.
"""
import math

SOURCE_COLORS=((255,59,48),(52,199,89),(0,122,255),(255,204,0))
ORDER={0:(0,1,2,3),90:(2,0,3,1)}
NAMES=('red','green','blue','yellow')


def need(value,reason):
    if not value:raise RuntimeError(reason)


def source_palette(decoded):
    need(decoded.get('width')==640 and decoded.get('height')==480
        and decoded.get('EXIF_applied_to_pixel_digest') is False,
        'EXACT_RAW_JPEG_SOURCE_GEOMETRY_REQUIRED')
    samples=decoded.get('quadrant_RGB_samples')
    need(isinstance(samples,list) and len(samples)==4,'FOUR_SOURCE_RGB_SAMPLES_REQUIRED')
    for actual,expected in zip(samples,SOURCE_COLORS):
        need(isinstance(actual,list) and len(actual)==3
            and all(type(v) is int and 0<=v<=255 for v in actual)
            and all(abs(a-b)<=4 for a,b in zip(actual,expected)),
            'GENERATED_JPEG_PALETTE_DIFFERS_FROM_FIXED_PATTERN')
    return tuple(tuple(x) for x in samples)


def verify_display(image,decoded,clockwise_degrees,kind):
    """Verify full photo or uniquely visible owned thumbnail, never both at once.

    Thumbnail proof identifies the asymmetric quadrant arrangement, including
    square crops; it makes no claim about the renderer's crop/scale algorithm.
    A controller must additionally bind the exact sole-row owned album.
    """
    need(type(clockwise_degrees) is int and clockwise_degrees in ORDER,'FIXED_ROTATION_REQUIRED')
    need(kind in ('full','thumbnail'),'EXPLICIT_RENDER_SCOPE_REQUIRED')
    need(image.mode=='RGB' and min(image.size)>=120,'SCOPED_IMAGE_SIZE')
    palette=source_palette(decoded)
    factor=max(1,math.ceil(max(image.size)/360))
    small=image.resize((image.width//factor,image.height//factor),resample=0)
    groups=[[] for _ in palette]
    for index,pixel in enumerate(small.getdata()):
        for color,target in enumerate(palette):
            if all(abs(pixel[j]-target[j])<=6 for j in range(3)):
                groups[color].append((index%small.width,index//small.width));break
    need(all(len(g)>=40 for g in groups),'FOUR_OWNED_QUADRANTS_REQUIRED')
    boxes=[]
    for points in groups:
        left=min(x for x,y in points);right=max(x for x,y in points)+1
        top=min(y for x,y in points);bottom=max(y for x,y in points)+1
        need(len(points)/((right-left)*(bottom-top))>=0.94,'QUADRANT_NOT_A_SOLID_RECTANGLE')
        boxes.append((left,top,right,bottom))
    tl,tr,bl,br=[boxes[i] for i in ORDER[clockwise_degrees]]
    need(tl[2]<=tr[0] and bl[2]<=br[0] and tl[3]<=bl[1] and tr[3]<=br[1],
        'OWNED_ROTATION_QUADRANT_ORDER_CHANGED')
    need(all(abs(a-b)<=2 for a,b in ((tl[0],bl[0]),(tr[0],br[0]),(tl[2],bl[2]),(tr[2],br[2]),
        (tl[1],tr[1]),(bl[1],br[1]),(tl[3],tr[3]),(bl[3],br[3]))),'QUADRANT_GRID_CHANGED')
    left=min(v[0] for v in boxes);top=min(v[1] for v in boxes)
    right=max(v[2] for v in boxes);bottom=max(v[3] for v in boxes)
    width=right-left;height=bottom-top;fraction=width*height/(small.width*small.height)
    need(sum(map(len,groups))/(width*height)>.84,'OWNED_IMAGE_INTERIOR_OCCLUDED')
    if kind=='full':
        aspect=640/480 if clockwise_degrees==0 else 480/640
        need(abs(width/height-aspect)<.065,'OWNED_IMAGE_ASPECT_CHANGED')
        primary,primary_scope,other_scope=(width,small.width,small.height) if clockwise_degrees==0 else (height,small.height,small.width)
        need(primary>=min(primary_scope*.70,other_scope*.90) and fraction>=.23,'THUMBNAIL_NOT_FULL_IMAGE')
    else:
        need(64<=width*factor<=512 and 64<=height*factor<=512 and fraction<.20,
            'BOUNDED_THUMBNAIL_REQUIRED')
    scale_x=image.width/small.width;scale_y=image.height/small.height
    bounds=[round(left*scale_x),round(top*scale_y),round(right*scale_x),round(bottom*scale_y)]
    return {'render_scope':kind,'clockwise_degrees':clockwise_degrees,'scope_size':list(image.size),
        'source_palette_RGB':[list(v) for v in palette],'palette_source':'generated_owned_JPEG_before_UI',
        'color_tolerance':6,'quadrant_order':[NAMES[i] for i in ORDER[clockwise_degrees]],
        'quadrant_counts':list(map(len,groups)),'sample_quadrant_bounds':[list(v) for v in boxes],
        'scope_pattern_bounds':bounds,'scope_fraction':fraction,
        'thumbnail_crop_algorithm_qualified':False,'EXIF_or_MediaStore_qualified_by_this_function':False,
        'full_image_verified':kind=='full','thumbnail_verified':kind=='thumbnail'}
