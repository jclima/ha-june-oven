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

## Maintainer controls

Changes to `main` must arrive through a pull request. After the documented
GitHub branch rule is applied, it requires the `validate` check, an approving
review, and up-to-date branches before merging. `CODEOWNERS` requires the
repository owner to review changes to the integration, automation, and
repository policy.

Install the development linter in this repository once, then run
`./scripts/verify` before committing:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install ruff
```

The tracked pre-commit and pre-push hooks can be enabled with
`git config core.hooksPath .githooks`; the pre-push hook refuses direct pushes
to `main`. Hooks are a local safety net, not a replacement for GitHub branch
protection.
