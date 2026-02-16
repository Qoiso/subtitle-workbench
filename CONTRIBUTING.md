# Contributing

Thanks for contributing to `Subtitle Workbench`.

## Development Flow

1. Create a feature branch from `dev`.
2. Keep commits focused and descriptive.
3. Run basic checks before opening PR:
   - `python -m compileall app tests`
   - `python -m pytest -q` (if test env is available)

## Pull Request Guidelines

1. Explain the user impact and scope.
2. Include screenshots/GIF for UI changes.
3. Mention any config or compatibility changes.

## Privacy and Repo Hygiene

1. Do not commit personal config snapshots.
2. Do not commit local media or private images.
3. Run `.\scripts\privacy_check.ps1` before release PRs.
