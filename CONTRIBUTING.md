# Contributing to homeassistant-neeo

Thanks for taking an interest. This project is still small; the goal
is to keep it that way - a focused library plus a Home Assistant
integration that does the obvious thing without surprises.

## What kind of contributions are welcome

- Bug fixes against the verified behaviour of NEEO Brain firmware
  `0.53.9` (April 2018, the last one before the product was
  discontinued).
- Documentation improvements - especially in `docs/NEEO_API_NOTES.md`,
  if you have a Brain on a different firmware and notice a deviation.
- Test cases that capture real Brain payloads we don't yet cover.
- HA-integration features that match the architectural principle:
  **no polling, push-driven via forward actions**.

## Local development

```bash
git clone git@github.com:magictom74/homeassistant-neeo.git
cd homeassistant-neeo

# Install in editable mode with dev extras
pip install -e ".[dev]"

# Run the three local checks - all must pass before opening a PR
ruff check pyneeo
mypy --strict pyneeo
pytest -q
```

CI runs the same three checks on Python 3.10, 3.11, and 3.12. If you
add a new dependency, make sure it's in `pyproject.toml`.

## Coding standards

- **Type hints everywhere.** The library passes `mypy --strict`; keep
  it that way. New public functions need full annotations including
  the return type.
- **Frozen dataclasses** for domain models. Brain state should be
  immutable from the consumer's perspective.
- **Defensive parsers.** The Brain returns mixed shapes (list vs dict,
  int vs string keys). `from_raw` classmethods should not raise on
  shape variance - parse what you can, drop what you can't.
- **No polling.** Discovery is push-driven via forward actions. If
  you need new state, find a push path on the Brain instead of adding
  a poll loop.
- **Tests for new code.** New endpoints in `client.py` need a respx
  mock test; new event types need a payload-based test in
  `test_events.py`.

## Reverse-engineering a new endpoint

Before adding an endpoint that isn't in `docs/NEEO_API_NOTES.md`:

1. Capture a real request/response pair against a Brain.
2. Add the pair to `docs/NEEO_API_NOTES.md` under "Verified Endpoints".
3. Add a respx-based test in `tests/test_client.py` with the captured
   payload.
4. Then implement the client method.

This keeps the codebase honest - everything in `client.py` has been
seen on a real Brain, not guessed from forum posts.

## Pull request checklist

- [ ] `ruff check pyneeo` is clean
- [ ] `mypy --strict pyneeo` is clean
- [ ] `pytest -q` is green
- [ ] New behaviour is covered by a test
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] If a Brain payload was reverse-engineered, the raw capture
  is in `docs/NEEO_API_NOTES.md`

## License

By contributing you agree that your contribution will be licensed
under the project's [MIT license](LICENSE).
