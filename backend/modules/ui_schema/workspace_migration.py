from __future__ import annotations

from pathlib import Path


def remove_obsolete_requirements_copy(root: Path) -> bool:
    """Remove the obsolete local requirements copy when source references are enabled.

    A workspace that has ``requirements_source.json`` uses the external requirements
    source model. In that model ``requirements.json`` is neither authoritative nor
    read by the module, so keeping a copied file is misleading and can pollute a
    freshly created workspace after an overlay installation.
    """
    source_path = root / "requirements_source.json"
    legacy_path = root / "requirements.json"
    if not source_path.is_file() or not legacy_path.is_file():
        return False
    legacy_path.unlink(missing_ok=True)
    return not legacy_path.exists()
