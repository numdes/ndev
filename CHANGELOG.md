## [0.10.1] - 2026-04-17

- fix missing return value in `remove_todo`

## [0.10.0] - 2026-04-01

- add `--src` and `--dst` aliases for `--origin` and `--destination` in release command
- deprecate `--origin` and `--destination` options
- allow `release` to work without `pyproject.toml` (copies source tree as-is)
- apply `common-ignores` to `copy_root` (previously only applied to `copy-local`)
- add scenario tests and document release scenarios in README

## [0.9.1] - 2025-12-17

- add ignores extension for copy-repo

## [0.9.0] - 2025-12-12

- add ignores extension for copy-repo

## [0.8.0] - 2025-12-11

- allow to use source (tar.gz) distribution for wheels download

## [0.7.1] - 2025-11-18

- add `uv` support in wheels download

## [0.6.1] - 2025-07-29

- create pyproject.toml instead of requirements.txt

## [0.5.3] - 2025-05-15

- debug wheels download

## [0.5.2] - 2025-05-15

- make platform specification for wheel optional

## [0.5.1] - 2025-04-29

- hotfix: apply patches before release

## [0.5.0] - 2025-04-29

- add `git sync` command
- update branches
- add dry-run mode for git sync
- add patches

## [0.4.1] - 2025-02-20

- pack this tool with uv
- add info about version

## [0.4.0] - 2024-10-18

- create `release` command that helps to copy files of the given repo to release one.