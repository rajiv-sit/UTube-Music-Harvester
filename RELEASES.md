# Release history

## v0.1.0 - 2026-01-18
- Added the production readiness checklist, MIT license, and CI/CD guidance so reviewers can assess the repository before calling it production.
- Documented the release expectations in `PRODUCTION.md` and linked to the timeline from `README.md`.
- Tagged this commit as `v0.1.0` so the tested state can be referenced as a semantic release.

## Release process
1. Update `pyproject.toml` with the new version and describe any user-facing changes in `PRODUCTION.md`, `README.md`, or this changelog.
2. Run `python -m pip install -e .[dev]` plus `python -m pytest` locally to verify the build and tests.
3. Tag the commit (`git tag -a vX.Y.Z -m "vX.Y.Z release"`) and push both commits and tags to the remote.
4. Create a GitHub release that references the tag (manually or via `gh release create`) and includes a summary of the user-visible changes.
