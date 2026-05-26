#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

path = Path('index.html')
text = path.read_text(encoding='utf-8')
severity_script = '<script src="severity-standardization.js?v=1"></script>'
map_script = '<script src="map-crossfilter.js?v=1"></script>'
climate_time_script = '<script src="climate-timestamp-fix.js?v=1"></script>'
sources_script = '<script src="dashboard-source-links.js?v=1"></script>'
anchor = '<script src="analytics-dashboard.js?v=3"></script>'

if severity_script not in text:
    if anchor in text:
        text = text.replace(anchor, severity_script + '\n' + anchor)
    else:
        text = text.replace('</body>', severity_script + '\n</body>')

if map_script not in text:
    if anchor in text:
        text = text.replace(anchor, map_script + '\n' + anchor)
    else:
        text = text.replace('</body>', map_script + '\n</body>')

if climate_time_script not in text:
    if anchor in text:
        text = text.replace(anchor, climate_time_script + '\n' + anchor)
    else:
        text = text.replace('</body>', climate_time_script + '\n</body>')

if sources_script not in text:
    if anchor in text:
        text = text.replace(anchor, anchor + '\n' + sources_script)
    else:
        text = text.replace('</body>', sources_script + '\n</body>')

path.write_text(text, encoding='utf-8')
