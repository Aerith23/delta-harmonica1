"""Fetch Spotify's pretrained ONNX model, verify against the pinned manifest."""
from pathlib import Path
import hashlib
import json
import urllib.request

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'model-manifest.json').read_text(encoding='utf-8'))
target = root / 'models' / 'basic_pitch.onnx'
target.parent.mkdir(exist_ok=True)
data = urllib.request.urlopen(manifest['url'], timeout=60).read()
if hashlib.sha256(data).hexdigest() != manifest['sha256']:
    raise RuntimeError('Model checksum mismatch')
temp = target.with_suffix('.download')
temp.write_bytes(data)
temp.replace(target)
print('Basic Pitch ONNX model is ready:', target)
