# Development compatibility sources

`python-runtime` is the Python reference used by native parity tests and demo
setup/reset utilities. It is never deployed as an agent skill.

`hermes-previous` preserves the pre-migration Hermes implementation and tests for
historical comparison. Those tests use their original layout and are not the
current runtime test suite. The supported runtime is the native executable in
`skills/productivity/chief-of-staff/scripts`; see its RUNTIME_README.md.
