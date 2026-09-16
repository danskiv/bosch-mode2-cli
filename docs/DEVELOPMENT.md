# Development Guide

## Repository Layout

```text
bosch-mode2-cli/
├── src/bosch_mode2_cli/       # Runtime package
├── tests/                     # Unit and simulator-backed integration tests
├── docs/                      # Architecture, runbooks, protocol and audit documents
├── config.example.yaml        # Non-secret configuration template
├── pyproject.toml             # Package metadata and dependencies
├── requirements.txt           # Runtime dependency list
├── run-monitor.ps1            # Windows source launcher
└── sync-to-laptop.sh          # Optional developer sync helper
```

## Environment Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

On Windows, use `.venv\\Scripts\\Activate.ps1` instead.

## Test and Validation Commands

```bash
pytest -q
python -m compileall -q src
 git diff --check
```

The simulator-backed tests do not contact a real panel. Field tests must be bounded, read-oriented, and performed with competing vendor clients disconnected.

## Local Simulator

Terminal 1:

```bash
bosch-mode2 simulate --port 17700 --pin LOCAL_TEST_CODE --auto-events
```

Terminal 2:

```bash
bosch-mode2 monitor --host 127.0.0.1 --port 17700 --pin LOCAL_TEST_CODE --no-tls --plain
```

The simulator exercises identity, authentication, status, history, point updates, area updates, and event output without changing a real alarm panel.

## Adding a Feature

1. Read the current README, architecture document, protocol specification, and relevant tests.
2. Define whether the feature is read-only or an action/control path.
3. Write a focused failing test first.
4. Implement the smallest change that makes the test pass.
5. Run the focused test, then the complete suite.
6. Check documentation and packaging references.
7. Run `git diff --check` and inspect `git status`.
8. Do not commit production credentials or raw sensitive captures.

## Protocol and Safety Rules

- Preserve the distinction between TCP, TLS, Mode 2 identity, authentication, status, and history.
- Do not infer authentication success from an open port or TLS handshake.
- Keep Solution 2000/3000 behavior separate from B/G and B426-M assumptions.
- Treat Solution 3000 as theoretical compatibility until a physical panel test records identity, authentication, status, history, and event-delivery results.
- Do not call the Solution 2000 simulator a Solution 3000 validation.
- Do not add arm/disarm, output, date/time, or configuration commands to a monitor without a separate safety review.
- Treat `SET_SUBSCRIPTION` and callbacks as event delivery mechanisms, not proof of universal realtime behavior.
- A laptop notification is not an alarm signaling path; never describe the CLI as a siren controller.

## Release Hygiene

Generated directories and release outputs are ignored:

- `.venv/`
- `__pycache__/`
- `.pytest_cache/`
- `*.egg-info/`
- `dist/`, `build/`, `portable/`
- `*.log`
