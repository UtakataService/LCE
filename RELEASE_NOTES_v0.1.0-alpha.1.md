# LCE v0.1.0-alpha.1

This is a packaging follow-up to `v0.1.0-alpha`.

## Added

- `pip` installation directly from the public GitHub repository.
- Release wheel asset: `lce_open_core-0.1.0a1-py3-none-any.whl`.
- Installed commands: `lce` for the bounded CLI and `lce-api` for the local
  Control API.
- `python -m lce_validation` module entry point.
- A clean-virtual-environment installation check for the wheel and all three
  command paths.

## Install

```powershell
python -m pip install "lce-open-core @ git+https://github.com/UtakataService/LCE.git@v0.1.0-alpha.1"
```

See [PIP_INSTALL.md](PIP_INSTALL.md) for release-wheel installation and the
command boundary.

## Scope

This changes packaging and distribution only. LCE remains an experimental,
bounded control layer; it is not an LLM, PyPI distribution, general chat
quality claim, or production service.
