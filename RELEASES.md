# 🏷️ BackseatCaster — Release Process

This project is pre-1.0; development happens on feature branches and lands on the main branch via PR. Versioning targets **[SemVer](https://semver.org/)** (`0.y.z` while the API contract settles) and generally follows **[Keep a Changelog](https://keepachangelog.com/en/1.1.0/)** conventions.

---

## 1. Versioning Rules

- **MAJOR:** breaking changes to the HTTP API contract (envelope shape, endpoint removal, schema field removal/renaming), the `manifest.json` schema, or stored DB state without a migration.
- **MINOR:** new endpoints, new render presets/quality tiers, new mining stages, UI capability additions.
- **PATCH:** bug fixes, performance, dependency bumps, docs-only changes (can be released quickly).
- Version lives in `app/config.py` → `Settings.VERSION` (displayed at `GET /`, `/docs`, and the OpenAPI `info` block). Bump it as part of the release commit.

---

## 2. Release Checklist

1. **Changelog:** add the new version heading + date to [CHANGELOG.md](CHANGELOG.md) with `Added / Changed / Fixed / Removed` sections; move the previous "Unreleased" items down.
2. **Version bump:** update `VERSION` in `app/config.py`.
3. **Quality gates (all green):**
   ```bash
   uv run pytest          # full suite
   uv run ruff check      # lint
   uv run ruff format     # formatting clean
   cd ui && npm run lint && npm run build
   ```
4. **Migrations:** verify `uv run alembic upgrade head` applies cleanly on a copy of a real `data/backseatcaster.db`.
5. **Smoke test end-to-end:** sync/download a VOD, run a render, poll status, check the manifest, (optionally) OAuth + upload flow.
6. **Tag:** `git tag -a vX.Y.Z -m "vX.Y.Z"` and `git push --tags`.
7. **Announce:** summarize the release in the CHANGELOG so it can be pasted into the GitHub Release notes.

---

## 3. Docker / Distribution

- Publication artifacts are the source tree plus `Dockerfile` / `docker-compose.yml`; consumer-facing "releases" are the state of `main` + tag.
- If/when images are published, pin base image digests and record image diffs per release here.

---

## 4. Pre-1.0 Caveats

- The `BaseResponse` envelope, highlight candidate schema, and `manifest.json` layout may still change in MINOR versions. Deployments should treat `data/` as regenerable-plugin, with expected loss of local state when format migrations land.
- See [ROADMAP.md](ROADMAP.md) for what is coming next and [docs/adr/](docs/adr/) for design decisions that constrain releases.
