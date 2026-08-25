# Public Release Checklist

Run this checklist before creating the first public repository or release.

## Ownership and legal decisions

- [ ] Choose and add a license after confirming that the maintainer owns or can
      redistribute all source, documentation, and bundled algorithm data.
- [ ] Confirm the project name, maintainers, support channel, and release
      version.
- [ ] Verify the redistribution terms for every bundled dataset and model
      reference. Do not publish downloaded imagery, user data, or derived
      catalogs without permission.
- [ ] Review attribution and terms for QGIS, OpenStreetMap, Sentinel Hub,
      USGS, AMap, and any LLM or embedding providers actually used.

## Secrets and history

- [ ] Rotate every credential that previously appeared in local configuration.
- [ ] Confirm `spatial_analysis_system/config.yaml` and
      `config/local_settings.py` are absent from the commit being published.
- [ ] Scan all staged files and Git history for API keys, tokens, passwords,
      email addresses, private endpoints, and personal paths.
- [ ] If a secret was committed or pushed before, revoke it and remove it from
      Git history with an appropriate history-rewrite process before publishing.

## Repository hygiene

- [ ] Confirm `.gitignore` excludes runtime outputs and local data.
- [ ] Build the Python environment from `requirements.txt` and the frontend
      from `web/package-lock.json` on a clean machine.
- [ ] Run the applicable Python tests, `npm run test`, and `npm run build`.
- [ ] Check that the examples in `README.md` and `docs/SETUP.md` work from a
      fresh clone.
- [ ] Verify CORS and file-serving paths are limited to trusted deployment
      needs before exposing the API.

## Publication

- [ ] Repair or recreate the local Git repository if `git status` cannot read
      `HEAD`; do not publish from a repository with invalid Git metadata.
- [ ] Create the public repository with an empty initial history only after the
      review above, or push a verified clean branch.
- [ ] Add repository topics, issue templates, a citation file if appropriate,
      and a release tag after the first reproducible build.
