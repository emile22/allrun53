import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
_RUNTIME_PATHS = (
    PROJECT_ROOT / "run.py",
    PROJECT_ROOT / "pyproject.toml",
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "netconf",
    PROJECT_ROOT / "yang",
    PROJECT_ROOT / "examples",
)
_TEXT_SUFFIXES = {".py", ".toml", ".json", ".xml", ".sh", ".ps1", ".yang"}


def test_runtime_inputs_do_not_reference_other_run_trees() -> None:
    for path in _RUNTIME_PATHS:
        files = [path] if path.is_file() else path.rglob("*")
        for item in files:
            if item.is_symlink():
                raise AssertionError(f"runtime symlink is not allowed: {item}")
            if not item.is_file() or item.suffix not in _TEXT_SUFFIXES:
                continue
            text = item.read_text(encoding="utf-8")
            run_names = set(re.findall(r"allrun\d+", text))
            assert run_names <= {"allrun53"}, (item, run_names)


def test_runtime_data_and_scripts_reside_under_allrun53() -> None:
    assert PROJECT_ROOT.name == "allrun53"
    assert (PROJECT_ROOT / "data" / "devices" / "instances.json").is_file()
    assert (PROJECT_ROOT / "scripts" / "wsl-netconf-start.sh").is_file()
    assert not (PROJECT_ROOT / ".venv").resolve().is_symlink()
