# Versioning and Release Policy

## Version source

This project uses one canonical runtime version:

```text
src/bosch_mode2_cli/__init__.py
```

`pyproject.toml` reads that value through `setuptools` dynamic metadata. Do not maintain a second independent version number in packaging metadata.

The current version is `0.1.0`.

## Semantic Versioning

Use `MAJOR.MINOR.PATCH`:

- **MAJOR** — an incompatible CLI, configuration, protocol, or public Python API change.
- **MINOR** — a backward-compatible feature or supported command/capability.
- **PATCH** — a backward-compatible bug fix, documentation correction, or internal improvement.

Before `1.0.0`, the project is still evolving. Minor releases may refine the CLI contract, but changes must be recorded clearly in the changelog and migration notes when user configuration or commands are affected.

## Change workflow

1. Create a focused feature branch.
2. Add or update tests before implementation where behavior changes.
3. Update the canonical version in `src/bosch_mode2_cli/__init__.py` only when preparing a release.
4. Add a changelog entry under `## [Unreleased]` during development.
5. Keep README and operational documentation consistent with the released behavior.
6. Run the verification gate:

   ```bash
   pytest -q
   python -m compileall -q src
   python -m pip install -e .
   bosch-mode2 --version
   git diff --check
   ```

7. Move the finalized entries from `Unreleased` into a versioned section with the release date.
8. Commit the release as one logical change.
9. Create an annotated Git tag:

   ```bash
   git tag -a v0.1.0 -m "Release v0.1.0"
   ```

10. Push the branch and tag only after review and explicit approval.

## Release gate

A release must have:

- passing automated tests;
- a successful package metadata/version check;
- no generated cache or populated local configuration committed;
- updated Windows runbook and README;
- an explicit statement of field-test status;
- no unverified claim that monitoring is universally push-realtime;
- no production credential, raw sensitive capture, or endpoint secret in the release.

## Git tags

Tags use the format:

```text
vMAJOR.MINOR.PATCH
```

Examples:

```text
v0.1.0
v0.2.0
v0.2.1
```

Do not reuse or move an existing release tag. If a release must be corrected, increment the patch version and create a new tag.

## Compatibility notes

Changes to these surfaces require special changelog notes:

- configuration path or YAML field names;
- visible connection wizard prompts;
- `--host`, `--port`, `--pin`, or subcommand behavior;
- TLS/plain transport defaults;
- history authority requirements;
- event timing, push subscription, or polling semantics;
- supported Python versions and dependency constraints;
- Windows launcher or portable distribution behavior.

## Current release status

`0.1.0` is the initial development release. The physical B426/Windows path has been exercised during engineering work, but every future release must state separately which layers were verified: route, TCP, TLS, Mode 2 identity, authentication, status, history, and live event delivery.
