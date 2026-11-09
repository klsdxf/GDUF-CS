import json
import sys
from PIL import Image,ImageChops
a,b=[Image.open(p).convert('RGB') for p in sys.argv[1:3]]
if a.size!=b.size:raise SystemExit('Image dimensions differ')
d=ImageChops.difference(a,b)
pixels=list(d.getdata())
print(json.dumps({'width':a.width,'height':a.height,'changed_pixels':sum(any(p) for p in pixels),'max_channel_delta':max(max(p) for p in pixels)}))
