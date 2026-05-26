#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

path = Path('index.html')
text = path.read_text(encoding='utf-8')
map_script = '<script src="map-crossfilter.js?v=1"></script>'
sources_script = '<script src="dashboard-source-links.js?v=1"></script>'
anchor = '<script src="analytics-dashboard.js?v=3"></script>'

if map_script not in text:
    if anchor in text:
        text = text.replace(anchor, map_script + '\n' + anchor)
    else:
        text = text.replace('</body>', map_script + '\n</body>')

if sources_script not in text:
    if anchor in text:
        text = text.replace(anchor, anchor + '\n' + sources_script)
    else:
        text = text.replace('</body>', sources_script + '\n</body>')

path.write_text(text, encoding='utf-8')
