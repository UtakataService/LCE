# Portability

This tree is a curated Git staging repository. It contains no workspace state,
local model files, virtual environments, private data directories, or machine
specific absolute paths.

## Supported Baseline

- Python 3.11 or later
- Git
- `pytest` for the development/test lane

The reference examples use only the Python standard library. Optional Ollama
integration requires a separately installed compatible local model and is not
needed for the quickstart or test suite.

## New-Machine Setup

```sh
git clone <repository-url> lce-open-core
cd lce-open-core
python -m venv .venv
```

Activate the environment using your operating system's normal method, then:

```sh
python -m pip install --upgrade pip setuptools
python -m pip install -e ".[dev]"
python examples/quickstart_open_core.py
python examples/reference_assurance_gateway.py
python -m lce_validation.api_server --host 127.0.0.1 --port 8789
python -m pytest -q
python scripts/verify_public_tree.py
```

## Deliberate Exclusions

- `.grenade/`, local experiment state, model caches, and local database files
- host names, private LAN addresses, credentials, personal directories, and
  user-specific configuration
- full historical `outputs/`; only the bounded evidence cited by the public
  documentation is included
- model weights and Ollama installation state

The repository is source-available under the bundled `LICENSE`. Individual
Users receive broad rights; Organizations need prior written approval. See
`LICENSE_POLICY.md` and `ORGANIZATIONAL_USE.md` before sharing or redistributing it.
