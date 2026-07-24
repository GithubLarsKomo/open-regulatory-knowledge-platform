# GitHub Codespaces

Open the repository on GitHub, select **Code → Codespaces → Create codespace on `feat/task-report-0001-per-json`**.

The container installs the project and development dependencies automatically with:

```bash
python -m pip install -e '.[dev]'
```

## Validate the workspace

```bash
pytest
python tools/spec_linter.py --strict
```

## Run the API

```bash
uvicorn orkp.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Codespaces forwards port `8000` automatically and labels it **ORKP FastAPI**.

## Current PER slice integration

Before completing the draft pull request, mount the router in `src/orkp/api/main.py`:

```python
from orkp.api.per_report_router import create_per_report_router
```

and in `create_app()`:

```python
app.include_router(create_per_report_router(get_repo))
```

Then run the complete test and linter commands again.
