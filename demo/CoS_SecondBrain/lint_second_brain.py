from pathlib import Path
import json, re
V=Path(r"C:\Users\NVIDIA\Documents\second brain")
md=list(V.rglob("*.md"))
maintained=[p for p in md if "raw" not in p.relative_to(V).parts and p.name not in {"SCHEMA.md","index.md","log.md"}]
slugs={p.stem for p in md}
required={"title","created","updated","type","tags","sources","status","confidence"}
broken=[]; front=[]; too_few=[]
for p in maintained:
    text=p.read_text(encoding="utf-8")
    fm=re.match(r"^---\n(.*?)\n---",text,re.S)
    if not fm:
        front.append(str(p.relative_to(V))); continue
    keys={m.group(1) for m in re.finditer(r"^([a-z_-]+):",fm.group(1),re.M)}
    if required-keys: front.append(f"{p.relative_to(V)} missing {sorted(required-keys)}")
    links=re.findall(r"\[\[([^\]|#]+)",text)
    if len(links)<2: too_few.append(str(p.relative_to(V)))
    for link in links:
        if link not in slugs: broken.append(f"{p.relative_to(V)}->{link}")
index=(V/'index.md').read_text(encoding='utf-8')
unindexed=[str(p.relative_to(V)) for p in maintained if p.stem not in re.findall(r"\[\[([^\]|#]+)",index) and p.name!='Home.md']
print(json.dumps({'markdown_files':len(md),'maintained_pages':len(maintained),'broken_links':broken,'frontmatter_issues':front,'pages_with_fewer_than_2_links':too_few,'unindexed':unindexed},indent=2))
