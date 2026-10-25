# Contributing

Please report reproducible problems with a small synthetic input and expected behavior.
Do not attach private logs or credentials. Discuss new syntax/dialects before adding them.

Use Python 3.11 or newer in an isolated virtual environment:

```text
python -m pip install -e . ruff==0.17.2 build==1.6.1
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m build
```

Tests should assert observable behavior, including CLI exit codes and invalid input.
Keep reports deterministic and terminal-safe. Keep package metadata and README limitations
consistent with the implementation. CI has read-only repository permissions and never
commits generated files. The project is maintained under the repository owner's identity.
