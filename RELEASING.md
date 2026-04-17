# Releasing finn-mcp

Releases are automated via GitHub Actions. Publishing to PyPI uses
[trusted publishing](https://docs.pypi.org/trusted-publishers/) — no API
tokens are stored in the repo.

## One-time setup (PyPI trusted publisher)

Before the first release, register this repo as a "pending publisher" on
PyPI so the package doesn't have to exist there yet.

1. Log in at https://pypi.org.
2. Go to **Your account → Publishing → Add a new pending publisher**.
3. Fill in:
   - **PyPI project name**: `finn-mcp`
   - **Owner**: `aHk-coder`
   - **Repository name**: `finn-mcp`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`
4. Save.

On the GitHub side, create a repository environment named `pypi`
(**Settings → Environments → New environment → pypi**). No secrets needed;
the `id-token: write` permission in the workflow handles authentication.

## Cutting a release

1. Bump `version` in `pyproject.toml` (SemVer).
2. Commit and push to `main`.
3. Tag the commit and push the tag:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

4. The `release` workflow runs automatically:
   - Builds the sdist and wheel with `uv build`.
   - Publishes to PyPI via OIDC trusted publishing.
   - Creates a GitHub Release with auto-generated notes and the dist files.

Users can then install with `uvx finn-mcp` or `pip install finn-mcp`.
