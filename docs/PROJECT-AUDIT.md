# Project Audit and Cleanup Record

## Scope

This audit covered the repository root, tracked/untracked files, runtime imports, tests, documentation, generated artifacts, and credential-like text references.

No external panel configuration was changed during this audit. No B426 connection or authentication test was run.

## Findings Before Cleanup

The repository root contained the core application together with a large temporary investigation workspace:

- approximately 30 one-off network, TLS, B426, A-Link, Windows, and protocol scripts;
- a Windows portable ZIP of approximately 25 MB;
- portable build/specification/readme files;
- generated `.pytest_cache`, `__pycache__`, and editable-install `egg-info` material;
- documentation that did not consistently describe the latest visible-code wizard;
- stale absolute Windows paths in diagnostic scripts.

## Cleanup Applied

| Change | Result |
|---|---|
| Remove field probes and audit helpers | Deleted; they were temporary investigation artifacts, not runtime dependencies |
| Remove portable build and smoke tooling | Deleted; the repository currently supports source execution only |
| Remove historical portable package | Deleted; it predated the latest wizard changes |
| Remove generated cache/install metadata | `.pytest_cache/`, `__pycache__`, `.pyc`, and editable-install metadata removed |
| Remove empty auxiliary directories | `tools/` and `release/` removed |
| Extend ignore rules | `portable/`, release ZIPs, logs, and generated directories remain ignored |
| Add English documentation | Architecture, Windows runbook, development guide, documentation index, and this audit |

## Current Supported Surface

The supported application surface is:

- `src/bosch_mode2_cli/`
- `tests/`
- `run-monitor.ps1`
- `verify_windows_cli.ps1`
- `README.md`
- `config.example.yaml`
- `docs/`
- `pyproject.toml`
- `requirements.txt`
- `sync-to-laptop.sh`

There are no retained diagnostic or portable-release directories in the repository after this cleanup.

## Verification

The last full runtime verification before the final deletion-only cleanup was:

```text
21 passed
python -m compileall -q src: PASS
git diff --check: PASS
```

After cleanup, run the same checks again before committing. Test execution will recreate ignored `__pycache__` and `.pytest_cache`; these are generated files, not project source.

## Follow-up Items

- Several simulator/unit-test defaults still use a test-only numeric code and internal compatibility parameters are still named `user_pin`. These are not production configuration, but should be addressed in a dedicated hardening change.
- Review old protocol/research claims against the exact panel/module firmware before treating them as normative.
- Do not commit a populated per-user `config.yaml`.
