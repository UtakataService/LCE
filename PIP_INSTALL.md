# Install with pip

LCE is distributed as the Python package `lce-open-core`. It is not published
to PyPI in this alpha release, so install it from the public GitHub repository
or from a release wheel.

## Requirements

- Python 3.11 or later
- `pip`

## Install from GitHub

```powershell
python -m pip install "lce-open-core @ git+https://github.com/UtakataService/LCE.git@v0.1.0-alpha.1"
```

For development from a clone:

```powershell
python -m pip install -e .
```

## Install the Release Wheel

Download the `lce_open_core-0.1.0a1-py3-none-any.whl` asset from the
[`v0.1.0-alpha.1` release](https://github.com/UtakataService/LCE/releases/tag/v0.1.0-alpha.1),
then install it locally:

```powershell
python -m pip install .\lce_open_core-0.1.0a1-py3-none-any.whl
```

## Commands

```powershell
lce --help
lce-api --host 127.0.0.1 --port 8789
python -m lce_validation --help
```

`lce` exposes the bounded utility and evidence commands documented in the
repository. `lce-api` starts the local Control API; it does not run a model,
call tools, or add authentication. See [API.md](API.md) for the caller-owned
integration boundary.

## Scope

The installation method does not change LCE's experimental status or its
bounded claims. See [CURRENT_STATUS.md](CURRENT_STATUS.md) and
[EVALUATION_POLICY.md](EVALUATION_POLICY.md).
