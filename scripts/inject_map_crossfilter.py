#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

path = Path('index.html')
text = path.read_text(encoding='utf-8')
script = '<script src="map-crossfilter.js?v=1"></script>'

if script not in text:
    if '<script src="analytics-dashboard.js?v=3"></script>' in text:
        text = text.replace(
            '<script src="analytics-dashboard.js?v=3"></script>',
            script + '\n<script src="analytics-dashboard.js?v=3"></script>',
        )
    else:
        text = text.replace('</body>', script + '\n</body>')

path.write_text(text, encoding='utf-8')
