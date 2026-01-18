# Production Readiness

This project currently powers a CLI, GUI, and optional voice layer over yt-dlp/FFmpeg, but a handful of production practices need to be explicit before you can treat it as a fielded product. The checks below document what “ready for production” means for UTube Music Harvester and what work remains.

## Release checklist

| Item | Status | Notes |
| --- | --- | --- |
| Semantic versioned releases | ❌ | Tag a new `vX.Y.Z` when the feature set stabilises and publish wheel/sdist artifacts on PyPI or GitHub Packages. |
| Release notes | ✅/❌ | Summarise user-facing changes, dependency bumps, and migration steps alongside each release. |
| Binary dependencies documented | ✅ | `README` lists ffmpeg/yt-dlp prerequisites; keep that section up to date when runtimes shift. |
| Upgrade policy | ❌ | Document how breaking API/CLI changes get versioned and communicated. |

## CI/CD & quality gates

- `python -m pip install -e .` (editable install) to ensure PYPROJECT dependencies build correctly.
- `python -m pytest` across supported Python versions (currently 3.11–3.14) as shown in `.github/workflows/ci.yml`.
- Consider adding coverage linting, formatter checks, and security scans to this pipeline before enabling branch protections.
- Enforce merge gates so PRs must pass CI before hitting `main`.

## Documentation & operational docs

1. Highlight production installation steps (virtualenv creation, dependency pinning, optional voice extras).
2. Document configuration controls (`UTUBE_*` environment variables) in either `.env.example` or a dedicated config reference (use `ARCHITECTURE.md` for deeper architecture notes).
3. Publish troubleshooting and monitoring guidance (e.g., how to inspect yt-dlp logs, where to look for `ffmpeg` warnings, voice model management).
4. Maintain a security/operations appendix that describes how to run `utube-gui`, how voice commands are handled, and what external services (YouTube, yt-dlp) this workload depends on.

## Security & legal considerations

- Clearly present the license (MIT by default, see `LICENSE`) so downstream consumers know usage rights.
- Warn users that harvesting YouTube content may violate YouTube’s Terms of Service depending on how the downloaded shots are used; let compliance/legal teams make the final call before deploying.
- Treat voice-related dependencies (sounddevice, Vosk models) as optional; document any additional privacy implications if microphone data is recorded or commands are stored.
- Record how proxies are managed (for example, the `src/utube/config.py` helper drops proxy env vars so yt-dlp/requests always use the expected network path).

## Next steps for production maturity

1. Automate releases (use `gh release create` or `twine upload`) after every milestone; include migration warnings when configuration names change.
2. Expand CI with security/formatting/packaging checks and publish badges in `README`.
3. Lock dependencies in a `requirements.txt` or `poetry.lock`/`pip-tools` file so deployments can reproduce builds.
4. Monitor runtime behavior (log ingestion, voice command errors) and document where to find logs after deployment.
