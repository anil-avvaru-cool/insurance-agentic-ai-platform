This file provides guidance to agents.

* **Configuration**: Use .env and example.env for configuration, never hardcoded values
* **Fail fast on config**: use `os.environ["KEY"]` (no defaults)
* **Naming standard**: underscores only (no hyphens)
* **Units**: Use USA standard units (miles, feet, pounds) in data and outputs
* **Use UV** for Python package management, running scripts, and test execution, pyproject.toml should be source of truth, do not use pip install, remove requirements.txt
* **Do not commit to git** Because User needs to review before commit