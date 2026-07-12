# Pack Trust Boundary

The current Open Core validates Pack content hashes and can require an exact,
active identity in a local `PackTrustStore`. Each pinned identity carries a Pack
ID, version, content hash, issuer ID, key ID, and revocation status.

## Current Guarantee

An unpinned or revoked Pack is rejected before it can be used by a trusted
integration. A content-hash mismatch is rejected by the existing Pack
validator before the trust decision.

## Deliberate Limitation

The current trust store is a local policy artifact. It does **not** verify a
detached public-key signature and does not establish trust in the distribution
of the trust store itself. Therefore automatic third-party Pack download and
public Pack distribution remain NO-GO.

## Next Release Gate

Before public third-party Pack distribution, LCE needs:

1. A documented detached public-key signature format and canonical signed
   payload.
2. A verified trust-root/keyring distribution method.
3. Key rotation, revocation, expiry, and rollback tests.
4. Release provenance and compatibility policy.
