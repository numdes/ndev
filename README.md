# ndev

ndev is an ultimate tool to manage development lifecycle.

- [managing releases](#release-management)
- _work in progress..._

To install `ndev` run:

```bash
uv tool install ndev
```

To update `ndev` run:

```bash
uv tool upgrade ndev
```

You can use it to install and debug:

```bash
git clone https://github.com/numdes/ndev 
cd ndev
uv tool install --editable .
```

## Release management

When you have a big repository with complicated structure, and you want to release it for
customers with a specific structure, you can use `ndev release` command.

```mermaid
flowchart LR
    SourceRepo[Source Repository]
    DestinationRepo[Destination Repository]
    SourceRepo -->|ndev release| DestinationRepo

```

Basic use case is to transfer some sources codes to another repository:

```bash
    ndev release \
        --src . \
        --dst git@example.com:libs/example1.git \
        --author_name "$GITLAB_USER_NAME" \
        --author_email "$GITLAB_USER_EMAIL"
```

Here `--src` is a path to the sources you want to release,
`--dst` is a path to the repository where you want to release the sources.

> **Note:** `--origin` / `--destination` still work but are deprecated.
> Use `--src` / `--dst` instead.

`--author_name` and `--author_email` are optional parameters that will be used
to set author of the commit in the destination repository.

After running this command, `ndev` will:

1. Wipe out all the files in the destination repository
2. Copy all the files from the origin repository to the destination repository
3. Commit all the changes

### Scenarios

#### Scenario #01 — plain directory copy

When the source contains only regular files and directories (no `pyproject.toml` in the
release root), `ndev release` copies the entire tree as-is to the destination:

```bash
ndev release --src ./src --dst ./dst
```

```
src/                 →  dst/
├── root_file.txt         ├── root_file.txt
├── subdir_a/             ├── subdir_a/
│   └── file_a.txt        │   └── file_a.txt
└── subdir_b/             └── subdir_b/
    └── file_b.txt            └── file_b.txt
```

See `tests/fixtures/02_plain_dirs` for the fixture and `tests/test_release_command.py::test_plain_dirs`
for the corresponding test.

#### Scenario #05 — common ignores

Files matching `common-ignores` patterns in `pyproject.toml` are excluded from the
destination during release. Patterns use glob syntax and apply to both `copy_root` and
`copy-local` operations:

```toml
[tool.ndev]
release-root = "release_root"
common-ignores = ["*.log", "secret.txt"]
```

```bash
ndev release --src ./project --dst ./dst
```

```
project/                          dst/
├── pyproject.toml
└── release_root/
    ├── keep.txt              →   ├── keep.txt
    ├── debug.log             →   │   (excluded)
    ├── secret.txt            →   │   (excluded)
    └── subdir/                   └── subdir/
        ├── nested.txt        →       └── nested.txt
        └── trace.log         →           (excluded)
```

See `tests/fixtures/05_common_ignores` for the fixture and
`tests/test_release_command.py::test_common_ignores` for the corresponding test.

### Configuration

All configuration is stored in `pyproject.toml` in `tool.ndev` section. Config sample:

```toml
[tool.ndev]
# relative path in origin repository to be a root of the release in destination repository
release-root = "releases/customer-root"

# generate and copy requirements.txt
copy-requirements = true

# manage pyproject.toml 
manage-pyproject = true

# generate poetry lock after all steps
generate-poetry-lock = true

# generate and copy version.json
add-version-json = true

# list of files to be copied from origin to destination
copy-local = [
    { from = "example1", to = "services/example1" },
]

# list of wheels to be copied from origin dependecies to destination
copy-wheel-src = [
    # wheels sources for external use
    { from = "example2", to = "wheels/example2" },
    # ignore some files while copying
    { from = "example2", to = "wheels/example2", ignores = ["*.txt", "README.md"] },
    # specify platform for the wheel. This is useful when you run `ndev release` 
    # on a different platform than the one you want to release for.
    { from = "example2", to = "wheels/example2", platform = "manylinux_2_36_x86_64" },
]

# list of repositories to be copied to destination
# if repo has ndev configuration, it will use it recursively
copy-repo-src = [
    { from = "git@example.com:collction/example3.git", to = "libs/example3/cpp-src", ref = "main" },
]

# below is an example of how to copy a repository with specific package name and platform
# it uses custom configuration for package name to follow specific tag
[[tool.ndev.copy-repo-src]]
from = "git@example.com:repo/example4.git"
to = "libs/example4/cpp-src"
ref = "$NAME$-$VERSION$"
package_name = "some_package_name"
platform = "manylinux_2_36_x86_64"

# patch files before release
[[tool.ndev.patches]]
glob = "**/_extern/pybind11/**"
regex = "https?:\\/\\/[^\\s)'\"]+"
subst = "LINK-REMOVED-DUE-TO-SECURITY-REQUIREMENTS"

```
