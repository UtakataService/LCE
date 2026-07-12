import json
from pathlib import Path

import pytest

from lce_validation.runtime.model_pack import load_pack
from lce_validation.runtime.pack_trust import PackTrustError, require_trusted_pack


PACK_PATH = Path("lce_validation/fixtures/reference_language_pack_frame_v1.json")


def _store(pack, status="active"):
    return {
        "store_id": "org.lce.test",
        "store_version": "1",
        "identities": [{
            "pack_id": pack["pack_id"], "pack_version": pack["pack_version"],
            "content_hash": pack["content_hash"], "issuer_id": "org.lce", "key_id": "test-key", "status": status,
        }],
    }


def test_exact_active_identity_pin_accepts_reference_pack():
    pack = load_pack(PACK_PATH)
    result = require_trusted_pack(pack, _store(pack))
    assert result["trusted"]
    assert result["issuer_id"] == "org.lce"


def test_untrusted_or_revoked_identity_fails_closed():
    pack = load_pack(PACK_PATH)
    with pytest.raises(PackTrustError, match="PACK_IDENTITY_UNTRUSTED"):
        require_trusted_pack(pack, {"store_id": "s", "store_version": "1", "identities": [{**_store(pack)["identities"][0], "content_hash": "sha256:" + "0" * 64}]})
    with pytest.raises(PackTrustError, match="PACK_IDENTITY_REVOKED"):
        require_trusted_pack(pack, _store(pack, status="revoked"))


def test_tampered_pack_never_reaches_trust_decision(tmp_path):
    pack = load_pack(PACK_PATH)
    raw = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    raw["payload"]["rules"][0]["patterns"].append("tampered")
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(Exception, match="PACK_CONTENT_HASH_MISMATCH"):
        require_trusted_pack(json.loads(path.read_text(encoding="utf-8")), _store(pack))
