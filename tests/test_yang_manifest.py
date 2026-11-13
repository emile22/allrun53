import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
MANIFEST_PATH = PROJECT_ROOT / "install" / "yang-module-manifest.json"


def test_yang_module_revisions_and_hashes_match_the_manifest() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    modules = manifest["modules"]
    assert len(modules) == 6

    for module in modules:
        path = (MANIFEST_PATH.parent / module["file"]).resolve()
        assert path.is_relative_to(PROJECT_ROOT)
        contents = path.read_bytes()
        assert hashlib.sha256(contents).hexdigest().upper() == module["sha256"]
        assert f"@{module['revision']}.yang" in path.name


def test_source_component_id_uses_the_yang_leafref_not_uuid_prose() -> None:
    path = PROJECT_ROOT / "yang" / "ietf-power-and-energy@2026-11-01.yang"
    contents = path.read_text(encoding="utf-8")
    assert 'path "/hw:hardware/hw:component/hw:name";' in contents
