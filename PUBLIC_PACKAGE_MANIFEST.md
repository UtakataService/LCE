# Public Package Manifest

## Included

| Path | Reason |
|---|---|
| `lce_validation/` | LCE implementation, data contracts, fixtures, and schemas. |
| `PIP_INSTALL.md` | pip installation contract and command surface. |
| `tests/` | Regression and public-contract verification. |
| `examples/` | Dependency-free Open Core and assurance demonstrations. |
| `profiles/gemma4_e4b_reference_profile_v1.json` | Versioned data-only local Ollama reference profile. |
| `GEMMA4_E4B_REFERENCE.md` | Same-candidate Gemma integration scope and reproduction command. |
| `RELEASE_NOTES_v0.1.0-alpha.md` | Candidate contents and known limits. |
| `.github/` | Portable CI and contribution templates. |
| Root documentation | Public scope, quickstart, release gates, and policy. |
| `evaluation/holdout_manifest_v1.json` | Metadata-only independent-holdout contract; no cases or gold outcomes. |
| `scripts/verify_holdout_manifest.py` | Enforces the public holdout manifest boundary. |
| `scripts/build_release_archive.py` | Builds the deterministic source ZIP outside Git tracking. |
| `scripts/verify_release_candidate.py` | Checks public release metadata and contact routes. |
| Selected `outputs/` | Current bounded capability, Gemma E4B integration, and public-readiness evidence. |

## Excluded

| Category | Examples |
|---|---|
| Workspace coordination | `.grenade/`, agent state, meetings, project logs. |
| Machine/runtime state | virtual environments, caches, `.lce_data/`, `.lce_runs/`. |
| Historical bulk reports | older `outputs/` reports not needed to understand or verify v0.1.0-alpha. |
| Local identity and network data | personal directories, host IDs, private LAN addresses, local service endpoints. |
| Models and secrets | model weights, Ollama state, credentials, local configuration. |

## Verification

Run `python scripts/verify_public_tree.py` after staging changes. The script
rejects known local-identity patterns, excluded runtime directories, and an
accidentally nested Git repository.
