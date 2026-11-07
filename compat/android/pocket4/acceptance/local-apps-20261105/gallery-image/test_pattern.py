from pathlib import Path
import importlib.util,unittest
from PIL import Image,ImageDraw

spec=importlib.util.spec_from_file_location('pattern',Path(__file__).with_name('verify_pattern.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def frame(size=(640,480),canvas=(800,700),reverse=False,missing=False):
    image=Image.new('RGB',(640,480),'black');draw=ImageDraw.Draw(image)
    colors=list(m.COLORS)
    if reverse:colors[0],colors[1]=colors[1],colors[0]
    for box,color in zip([(8,8,311,231),(328,8,631,231),(8,248,311,471),(328,248,631,471)],colors):
        draw.rectangle(box,fill=color)
    draw.rectangle((312,8,327,471),fill='white');draw.rectangle((8,232,631,247),fill='white')
    if missing:draw.rectangle((328,248,631,471),fill='black')
    image=image.resize(size,resample=0);background=Image.new('RGB',canvas,(17,17,17))
    background.paste(image,((canvas[0]-size[0])//2,(canvas[1]-size[1])//2));return background

class Boundaries(unittest.TestCase):
    def test_full_pattern_with_letterboxing(self):
        self.assertTrue(m.verify_pattern(frame())['full_pattern_verified'])
    def test_thumbnail_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'THUMBNAIL'):m.verify_pattern(frame(size=(160,120)))
    def test_wrong_order_and_missing_quadrant_rejected(self):
        for args in ({'reverse':True},{'missing':True}):
            with self.subTest(args=args),self.assertRaises(RuntimeError):m.verify_pattern(frame(**args))
    def test_stretched_geometry_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'ASPECT'):m.verify_pattern(frame(size=(640,300)))

if __name__=='__main__':unittest.main(verbosity=2)
