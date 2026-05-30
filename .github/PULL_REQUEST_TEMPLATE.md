<!-- Thanks for the PR. Keep it focused; small PRs land faster. -->

## Summary

<!-- One or two sentences on what this changes. -->

## Why

<!-- The motivation. If this fixes a bug, link the issue. -->

## Notes for reviewers

<!-- Anything non-obvious: a Brain quirk, a payload shape that
     surprised you, a tradeoff between two approaches you weighed. -->

## Checklist

- [ ] `ruff check pyneeo` is clean
- [ ] `mypy --strict pyneeo` is clean
- [ ] `pytest -q` is green
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] If a new Brain endpoint or payload was reverse-engineered, the
      raw capture is in `docs/NEEO_API_NOTES.md`
