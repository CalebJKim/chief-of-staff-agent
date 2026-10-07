"""Resolve explicit baseline link bindings; never infer a resource from a name."""
import json
import re
from reset_modes import evidence_from_state


def refresh_links(vault, demo, state):
    bindings = demo / "templates/second-brain-links.json"
    if not bindings.exists():
        return 0
    evidence = evidence_from_state(state)
    replacements = {}
    for original, binding in json.loads(bindings.read_text(encoding="utf-8")).items():
        if binding[0] == "email":
            target = evidence.get(binding[1])
        else:
            item = state
            for part in binding:
                item = item.get(part, {})
            target = item.get("url") if isinstance(item, dict) else None
        if not target:
            raise RuntimeError(f"Cannot resolve Second Brain source {binding}; baseline was not installed.")
        replacements[original] = target
    count = 0
    # One pass prevents a new URL being mistaken for another old URL.
    pattern = re.compile("|".join(re.escape(url) for url in sorted(replacements, key=len, reverse=True)))
    for path in vault.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        changed, matches = pattern.subn(lambda match: replacements[match[0]], text)
        if changed != text:
            path.write_text(changed, encoding="utf-8")
        count += matches
    return count
