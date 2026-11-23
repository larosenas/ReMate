## What

## Why

Related issue or use case: <!-- e.g. #12, CU-004 -->

## How it was tested

## Risks and side effects

## Checklist

- [ ] Tests added or updated, and all checks pass (`pytest --cov`, `ruff check .`, `ruff format --check .`, `npm run test:cobertura`, `npm run lint`, `npm run build`)
- [ ] If the models changed: migration added and `alembic check` reports nothing pending
- [ ] If the dependencies changed: audit without known vulnerabilities (`python scripts/auditar_dependencias.py` and `npm audit`)
- [ ] Diff reviewed: no accidental changes, secrets or real data
- [ ] Documentation updated
- [ ] I can explain every line of the change, including any code generated with AI
