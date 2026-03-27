# Contributing to oVirt MCP Server

Thank you for your interest in contributing to oVirt MCP Server!

This document describes how to contribute to this project.

## Commit Message Format

This project follows the [Conventional Commits](https://www.conventionalcommits.org/) specification. Every commit message must follow this format:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Type

Must be one of the following:

| Type | Description |
|------|-------------|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation only changes |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or correcting tests |
| `chore` | Changes to the build process, tooling, or auxiliary tools |

### Scope

The scope could be anything specifying the place of the commit change. For example: `server`, `cli`, `auth`, `config`, etc.

### Description

A short description of the change (max 72 characters).

### Examples

```
feat(server): add support for VM snapshot management

fix(auth): handle token expiration gracefully

docs(readme): update installation instructions
```

## Signed-off-by Requirement

Every commit must include a `Signed-off-by` line. This is a requirement for the project.

Use the `-s` flag when making commits:

```bash
git commit -s -m "feat(server): add new feature"
```

Or add the line manually to your commit message:

```
feat(server): add new feature

Signed-off-by: Joey Ma <majunjie@apache.org>
```

## Development Setup

### Prerequisites

- Python 3.10 or later
- pip

### Install Development Dependencies

```bash
pip install -e ".[dev]"
```

### Code Formatting (Ruff)

This project uses [Ruff](https://github.com/astral-sh/ruff) for linting.

Run linting:

```bash
ruff check .
```

Format code:

```bash
ruff format .
```

## Testing

### Running Tests

```bash
pytest
```

### Integration Tests

Integration tests are marked with the `integration` marker. They require a real oVirt/RHV connection and are skipped by default.

To run all tests including integration tests:

```bash
pytest --integration
```

**Requirement**: Non-integration tests must always pass. All tests in the CI pipeline must pass before merging.

## Pull Request Workflow

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:

   ```bash
   git clone https://github.com/<your-username>/ovirt-mcp-server.git
   cd ovirt-mcp-server
   ```

3. **Create a branch** for your changes:

   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

4. **Make your changes**, following the commit message format described above

5. **Run tests and linting** to ensure everything passes:

   ```bash
   pytest
   ruff check .
   ```

6. **Push** your branch to your fork:

   ```bash
   git push origin feature/your-feature-name
   ```

7. **Open a Pull Request** on GitHub

   - Reference any related issues using the `Fixes #123` or `Closes #123` syntax
   - Fill in the PR template completely

## Bug Reports

When reporting bugs, please include:

- A clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- oVirt/RHV version being used
- Python version
- Relevant log output

You can use the [Bug Report](.github/ISSUE_TEMPLATE/bug_report.md) template.

## Feature Requests

We welcome feature requests! Please use the [Feature Request](.github/ISSUE_TEMPLATE/feature_request.md) template.

## License

By contributing to oVirt MCP Server, you agree that your contributions will be licensed under the MIT License.
