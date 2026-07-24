# Contributing

Thanks for helping improve June Oven for Home Assistant.

## Before opening an issue

- Confirm the issue still occurs on a supported Home Assistant release.
- Enable debug logging for `custom_components.june_oven`.
- Download integration diagnostics when possible.
- Remove oven IDs, pairing codes, camera URLs, tokens, passwords, signing
  seeds, and any other credentials before sharing logs or screenshots.

Do not test heating commands on an unattended or obstructed oven.

## Pull requests

Keep changes focused and include tests for protocol or state-handling changes.
Run these checks before opening a pull request:

```bash
python3 -m compileall -q custom_components tests
python3 -m unittest discover -s tests -v
ruff check custom_components tests
ruff format --check custom_components tests
```

Changes that affect pairing, heating, cancellation, or camera access should say
whether they were verified on a physical oven. Never commit `.storage`,
diagnostic downloads, pairing codes, or credentials.
