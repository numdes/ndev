# ndev

Set of tools that helps to manage development lifecycle. This set contains tools for:

- [managing releases](#release-management)
- _work in progress..._

To install `ndev` run:

```bash
pipx install ndev
```

To update `ndev` run:

```bash
pipx upgrade ndev
```

## Release management

When you have a big repository with complicated structure and you want to 
make release of some part of it, you can use `ndev` to help you with that.

Basic use case is to transfer some sources codes to antoher repository:

```bash
    ndev release \
        --origin . \
        --destination git@example.com:libs/example1.git \
        --author_name "$GITLAB_USER_NAME" \
        --author_email "$GITLAB_USER_EMAIL"
```

Here `--origin` is a path to the sources you want to release, 
`--destination` is a path to the repository where you want to release the sources.

`--author_name` and `--author_email` are optional parameters that will be used 
to set author of the commit in the destination repository.

After running this command, `ndev` will:
1. Wipe out all the files in the destination repository
2. Copy all the files from the origin repository to the destination repository
3. Commit all the changes

All configuration is stored in `pyproject.toml` in `tool.ndev` section. Config sample:

```toml
[tool.ndev]
# relative path in origin repository to be a root of the release in destination repository
release-root = "releases/customer-root"

# generate and copy requirements.txt
copy-requirements = true

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
]
# list of repositories to be copied to destination
copy-repo-src = [
    { from = "git@example.com:collction/example3.git", to = "libs/example3/cpp-src", ref = "main" },
]
```