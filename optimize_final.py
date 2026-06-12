import pikepdf
import re
import sys
import os
from collections import defaultdict

input_path = sys.argv[1] if len(sys.argv) > 1 else 'asup31.ai'
base = input_path.rsplit('.', 1)[0]
output_path = f'{base}_optimized.pdf'

pdf = pikepdf.open(input_path)
page = pdf.pages[0]
xobjects = page.Resources.get('/XObject', {})

# --- Parse XObject streams, group by (header, drawing) ---
shape_groups = defaultdict(list)

for name, xobj in xobjects.items():
    raw = bytes(xobj.read_bytes()).decode('latin-1')
    match = re.match(
        r'(.*?)q 1 0 0 1 ([0-9.\-]+) ([0-9.\-]+) cm\n(.*?)\nQ\s*$',
        raw, re.DOTALL
    )
    if not match:
        continue
    header, tx_str, ty_str, drawing = match.groups()
    bbox = [float(xobj['/BBox'][i]) for i in range(4)]
    shape_groups[(header, drawing)].append(
        (str(name), xobj, float(tx_str), float(ty_str), bbox)
    )

# --- Put shared GS0 in page ExtGState ---
shared_gs0 = pdf.make_indirect(pikepdf.Dictionary({
    '/AIS': False, '/BM': pikepdf.Name.Normal, '/CA': 1.0,
    '/OP': False, '/OPM': 1, '/SA': True,
    '/SMask': pikepdf.Name('/None'), '/Type': pikepdf.Name.ExtGState,
    '/ca': 1.0, '/op': False,
}))
page.Resources['/ExtGState']['/GS0'] = shared_gs0

# --- Create template Form XObjects in page Resources ---
page_xobjects = page.Resources.get('/XObject', {})
template_keys = {}

for idx, ((header, drawing), items) in enumerate(shape_groups.items()):
    tpl_key = f'/Tpl{idx}'
    _, _, tx0, ty0, bbox0 = items[0]
    local_bbox = [bbox0[i] - (tx0 if i % 2 == 0 else ty0) for i in range(4)]

    tpl = pikepdf.Stream(pdf, f'{header}{drawing}\n'.encode('latin-1'))
    tpl['/Subtype'] = pikepdf.Name('/Form')
    tpl['/BBox'] = pikepdf.Array(local_bbox)
    tpl['/Matrix'] = pikepdf.Array([1, 0, 0, 1, 0, 0])
    # No Resources/Group — inherited from page
    page_xobjects[tpl_key] = pdf.make_indirect(tpl)
    template_keys[(header, drawing)] = tpl_key

# --- Rewrite each XObject as minimal wrapper ---
for (header, drawing), items in shape_groups.items():
    tpl_key = template_keys[(header, drawing)]
    for name, xobj, tx, ty, bbox in items:
        local = [bbox[i] - (tx if i % 2 == 0 else ty) for i in range(4)]
        xobj.write(f'{tpl_key} Do\n'.encode('latin-1'))
        xobj['/Matrix'] = pikepdf.Array([1, 0, 0, 1, tx, ty])
        xobj['/BBox'] = pikepdf.Array(local)
        for key in ['/Resources', '/Group']:
            if key in xobj:
                del xobj[key]

# --- Remove AI private data ---
for key in ['/PieceInfo', '/Thumb']:
    if key in page:
        del page[key]

pdf.save(output_path,
    object_stream_mode=pikepdf.ObjectStreamMode.generate,
    compress_streams=True)

orig = os.path.getsize(input_path)
opt = os.path.getsize(output_path)
print(f'{orig/1024/1024:.1f} MB -> {opt/1024/1024:.1f} MB ({(1-opt/orig)*100:.0f}% reduction)')
print(f'Saved: {output_path}')
