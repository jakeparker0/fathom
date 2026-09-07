# ADR-008: Dependency Management Tool and Python Version

**Status:** Accepted
**Date:** 2026-09-07

## Context

Fathom needs a Python dependency management approach beyond bare `pip`, which offers no environment management, no dependency locking, and no real resolver — `pip freeze` output is a flat, unstructured list that doesn't distinguish direct dependencies from transitive ones and gives no reproducibility guarantee across machines.

A companion decision is which Python version to target. This matters more than usual here because Sprint 5 (Analysis & Forecasting) depends on a scientific-computing-adjacent stack (Prophet, ARIMA, likely numpy/scipy/statsmodels underneath), and these ecosystems are historically slower to certify support for brand-new Python releases due to compiled C-extension dependencies.

The two decisions were made together because the Python version choice was made largely in service of the dependency-tool ecosystem risk assessment.

## Options Considered

### Dependency tool

#### Option A: Poetry
- Pros: Established, mature plugin ecosystem (dynamic versioning, requirements.txt export, etc.), widely adopted.
- Cons: Slower dependency resolution and installs than uv. Plugin ecosystem largely solves problems relevant to published packages (PyPI distribution, versioning from git tags) which don't apply to a single-user app deployed directly to one OCI instance.

#### Option B: uv
- Pros: Significantly faster install/resolution. Single tool also handles Python version installation and pinning natively, removing the need for a separate `pyenv`-style tool. Modern default for new Python projects. `pyproject.toml`-native, standards-compliant.
- Cons: Newer tool, smaller (but fast-growing) plugin ecosystem than Poetry. Not a real drawback given this project never publishes to PyPI and doesn't need Poetry's plugin-specific features.

### Python version

#### Option A: 3.14 (latest at time of decision)
- Pros: Newest language features and performance improvements. No legacy constraint since this is a new project.
- Cons: Released ~2 months prior to this decision. Higher risk that scientific-computing packages needed for Sprint 5 forecasting (Prophet, ARIMA, and their compiled dependencies) don't yet have mature, well-tested wheels for this version.

#### Option B: 3.12
- Pros: Two years mature at time of decision. High confidence that all plausible dependencies, including the Sprint 5 forecasting stack, have solid, well-tested support. Removes an entire class of "is this my bug or an immature package" ambiguity during development.
- Cons: Misses newer language features introduced in 3.13/3.14. Not a meaningful cost for this project.

## Decision

**uv**, chosen over Poetry for speed, built-in Python version management, and fit with a standards-based `pyproject.toml` workflow.

**Python 3.12**, chosen over 3.14, specifically to de-risk the Sprint 5 forecasting dependency stack (Prophet, ARIMA, and underlying scientific-computing packages), which are the components most likely to lag behind on new-Python-version support due to compiled extensions.

## Consequences

- `pyproject.toml` and `uv.lock` are the source of truth for dependencies; both are committed, giving fully reproducible installs (`uv sync`) from a clean clone.
- `.python-version` is committed (explicitly not gitignored) so the pinned interpreter version travels with the repo rather than depending on whatever Python happens to be installed on a given machine.
- Choosing 3.12 over 3.14 is a conservative choice with low switching cost: bumping `requires-python` upward later, if 3.14 ecosystem support matures before Sprint 5, is a cheap change. The reverse — hitting an immature-package wall mid-Sprint-5 on 3.14 — would have been more disruptive.
- Dev-only dependencies (`ruff`, `pytest`) are declared in a separate `[dependency-groups]` section, keeping them out of what would ship in a production install.

## Notes

Decided as part of S1-02 (Python project scaffold task). Superseding consideration: if a future sprint hits a hard dependency that requires 3.13+, this ADR should be revisited rather than silently overridden.