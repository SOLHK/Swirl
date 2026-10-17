"""Checked source maintenance for the native core branch; no workflow changes."""
from pathlib import Path
path = Path('core/crates/swirl-subscription/src/inspect.rs')
text = path.read_text(encoding='utf-8')
# WS now has both dedicated positive and negative tests. Retain these older
# unsupported-transport assertions using gRPC, which is still not implemented.
text = text.replace('            "&type=ws",', '            "&type=grpc",')
old = '"password":"s","network":"ws"},{"type":"trojan"'
new = '"password":"s","network":"grpc"},{"type":"trojan"'
text = text.replace(old, new)
path.write_text(text, encoding='utf-8')
