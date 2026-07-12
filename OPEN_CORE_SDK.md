# Open Core SDK

`lce_validation.open_core.OpenCoreSdk` is the small public facade for the
data-only Open Core reference path.

```python
from lce_validation.open_core import OpenCoreSdk

sdk = OpenCoreSdk("lce_validation/fixtures")
locked = sdk.lock_profile("lce_validation/fixtures/reference_profile_frame_v1.json")
reference = locked["pack_refs"][0]
report = sdk.run_language_conformance(
    reference["pack_id"], reference["pack_version"], reference["content_hash"],
    "lce_validation/fixtures/open_core_frame_parity_v1.jsonl",
)
```

## Supported Operations

- Resolve a local JSON Pack by ID, version, and content hash.
- Lock a local Profile to the exact Pack identities it references.
- Run the bounded language-Pack conformance fixture.
- Produce a frozen legacy-vs-Pack difference ledger.

## Deliberate Limits

- No arbitrary plugin loading or executable Pack hooks.
- No network Pack download, third-party signature verification, or keyring.
- No general dialogue route replacement or persistent state commit.
- No assertion that a conformance pass proves language understanding.

For the executable reference path, see [QUICKSTART.md](QUICKSTART.md). For the
trust boundary, see [PACK_TRUST.md](PACK_TRUST.md).
