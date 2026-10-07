# Retired Python runtime

Preserved as a compatibility oracle for `tests/native_parity.py` and formatting
fixture generation. This directory is **not bundled with the Perplexity skill**
and is not a runtime fallback. The demo reset utility still imports `credentials`
from `scripts/actions.py`; reset/setup tooling is outside the skill migration.

The archived launchers and tests document the previous implementation. Native
runtime tests live in `skills/productivity/chief-of-staff/native` and
`setup/perplexity/test_runtime.py`.
