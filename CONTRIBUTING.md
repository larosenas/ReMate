# Contributing to ReMate

Thanks for your interest. ReMate is a portfolio project maintained by one person, so the scope is small, but bug reports, questions and focused pull requests are welcome.

## Before you start

- **Bugs and ideas:** open an [issue](../../issues/new/choose) using one of the templates. For anything bigger than a small fix, open an issue first so we can agree on the approach before you write code.
- **Security problems:** do not open a public issue. Follow [SECURITY.md](SECURITY.md).
- **Language:** issues and pull requests can be written in English or Spanish. The code, the comments and most of the documentation are in Spanish.

## Development setup

Follow [Getting started](README.md#getting-started-development) in the README: Python 3.15, Node.js 24 LTS and PostgreSQL 18, with the configuration in a `.env` file copied from [`.env.example`](.env.example).

Turn on the secret scan before each commit, once per clone:

```sh
git config core.hooksPath scripts/hooks
```

## Making a change

1. Fork the repository and create a branch from `main`.
2. Keep the change small and focused on one purpose. Avoid unrelated refactors.
3. Add or update tests for any change in behaviour. For a bug fix, first add a test that reproduces the bug.
4. If the change affects a use case, reference it (`CU-001` to `CU-010`, see [docs/casos-de-uso/](docs/casos-de-uso/)) in the commit message and the pull request.
5. For a lasting architectural decision, add an ADR in [docs/adr/](docs/adr/).
6. Update the documentation when behaviour, configuration or installation changes.

## Checks

These must pass before a pull request is reviewed. The [CI workflow](.github/workflows/ci.yml) runs them too.

```sh
# Backend, inside backend/
pytest --cov
ruff check .
ruff format --check .

# Frontend, inside frontend/
npm run test:cobertura
npm run lint
npm run build
```

Tests must be deterministic: no real network, no real AI or mail server, and no dependence on the current date.

## Commit messages

Short, in the imperative, with a type and the use case when it applies, for example `feat(CU-004): read the payment terms from the quote`. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

## Code of conduct

By taking part you agree to follow the [code of conduct](CODE_OF_CONDUCT.md).
