# LCE Component Map

This map describes the public-alpha components, their ownership, and their
current claim boundary.

| Component group | Responsibility | Current maturity |
|---|---|---|
| `OpenCoreSdk` and Pack repository | Load local data-only Packs, lock a profile by identity/hash, and run conformance | Experimental GO; local JSON only. |
| Profile / Pack contracts | Separate configuration and surface data from Core behavior | Bounded GO; Packs cannot execute code or weaken Core invariants. |
| Semantic mapping and frame extraction | Map explicit surface forms into bounded labels and meaning points | Bounded GO; not general multilingual understanding. |
| Conversation state and trace | Keep bounded state, deterministic hashes, and replay data | Bounded GO; not a general memory system. |
| Hypothesis and response planning | Represent declared alternatives and withhold unsupported hypotheses | Foundation/Bounded; not free-form reasoning. |
| `StructuredOutputGateway` | Parse, validate, safely default optional fields, retry once, and reject bounded JSON contracts | Bounded GO; no truth or general intent guarantee. |
| `StructuredAssurancePolicy` | Check declared value, term, certainty, and evidence-reference rules | Bounded GO; lexical/declared checks only. |
| Candidate assurance | Accept, warn, hold, or reject typed adapter/sensor/rule candidates | Bounded GO; external detector quality is outside LCE. |
| Grading assurance | Audit declared score records and evidence/calibration requirements | Bounded GO; does not grade content itself. |
| Acceptance challenge | Pause an accepted result when declared cross-check or evidence signals disagree | Bounded GO; does not infer unknown semantic errors. |
| Ollama adapters | Obtain a model candidate and send it through LCE output gates | Bounded GO; model safety and language quality remain model-owned. |
| Foundation knowledge | Load low-risk authored JSONL definitions | Bounded GO; pattern retrieval only. |
| Pack trust store | Pin exact local identities and reject revoked identities | Foundation only; no signature/key distribution. |
| External ControlPack | Define routing and adapter plans as data | Foundation only; not a general autonomous router. |

## Invariants

The following remain Core-owned and cannot be disabled by a Pack or model
candidate: schema validation, state bounds, trace/replay shape, profile hash
locking, and configured authorization/evidence gates.

## Intentionally Missing

Detached signatures, third-party Pack distribution, MySQL Pack storage,
arbitrary plugin execution, public service operation, and a general learned
language model are outside the v0.1.0-alpha surface.
