"""Regenerate offline formatting contract cases from the preserved Python backend."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/productivity/chief-of-staff'
reference = ROOT / 'compat/python-runtime/scripts'
sys.path.insert(0, str(reference if reference.exists() else SKILL / 'scripts'))
import workspace_formatting as f

paragraph = {'startIndex': 1, 'endIndex': 10, 'paragraph': {'elements': [{'startIndex': 1, 'endIndex': 10, 'textRun': {'content': '😀 Target', 'textStyle': {}}}], 'paragraphStyle': {'namedStyleType': 'NORMAL_TEXT'}}}
styles = {'styles': [{'namedStyleType': 'NORMAL_TEXT', 'textStyle': {'foregroundColor': {'color': {'rgbColor': {'red': .2}}}, 'underline': True}}]}
doc = {'body': {'content': [paragraph]}, 'namedStyles': styles}
tabs = {'tabs': [{'tabProperties': {'tabId': 'tab1'}, 'documentTab': doc, 'childTabs': [{'tabProperties': {'tabId': 'child'}, 'documentTab': {'body': {'content': [{'table': {'tableRows': [{'tableCells': [{'content': [paragraph]}]}]}}]}, 'namedStyles': styles}}]}]}
text = {'textElements': [{'startIndex': 0, 'endIndex': 6, 'paragraphMarker': {'style': {'alignment': 'START'}, 'bullet': {'glyph': '1.'}}}, {'startIndex': 0, 'endIndex': 6, 'textRun': {'content': 'Target', 'style': {'foregroundColor': {'opaqueColor': {'rgbColor': {'blue': 1}}}}}}]}
slide = {'slides': [{'objectId': 'slide1', 'pageElements': [{'objectId': 'group', 'elementGroup': {'children': [{'objectId': 'shape', 'shape': {'text': text}}]}}, {'objectId': 'table', 'table': {'tableRows': [{'tableCells': [{'text': text}]}]}}]}]}
cases = []
for kind, data in [('docs', doc), ('docs', tabs), ('slides', slide)]:
    records = f.doc_records(data) if kind == 'docs' else f.slide_records(data)
    for style in [{'bold': True, 'font_size': 18, 'alignment': 'CENTER'}, {'list': 'numbered', 'space_before': 10}, {'link': 'https://example.com'}, {'link': None, 'color': '#00FF80', 'underline': False}]:
        matches = f.locate(records, 'Target', True)
        cases.append({'kind': kind, 'data': data, 'records': records, 'style': style, 'requests': f.make_requests(kind, matches, style)})
path = SKILL / 'native/tests/formatting.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'{len(cases)} formatting cases')
