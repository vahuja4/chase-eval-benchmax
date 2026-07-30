"""Per-backend env-bundle directory resolution.

Bundles live in bundles/{backend}/ so the local and Castform (postgres)
bundle sets coexist — switching backends never clobbers the other set.
Backend selection follows the same SEARCH_BACKEND env var the builder
and test_linker.py already use. See notes/rollout_interface.md D8.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
BUNDLES_ROOT = PROJECT_DIR / "bundles"
VALID_BACKENDS = ("local", "postgres")

_REBUILD_HINT = "Build it with: SEARCH_BACKEND={backend} python build_env_bundle.py"


def search_backend(backend: str | None = None) -> str:
    """Resolve the active search backend (explicit arg > env var > 'local')."""
    resolved = backend or os.environ.get("SEARCH_BACKEND", "local")
    if resolved not in VALID_BACKENDS:
        raise ValueError(
            f"Unknown SEARCH_BACKEND {resolved!r}; expected one of {VALID_BACKENDS}."
        )
    return resolved


def bundle_dir(backend: str | None = None) -> Path:
    """Directory holding the bundle set for the given/active backend."""
    return BUNDLES_ROOT / search_backend(backend)


def require_bundle(stem: str, backend: str | None = None) -> tuple[Path, Path]:
    """Return verified (pkl_path, metadata_path) for a bundle.

    ``stem`` is "env" (SearchEnv) or "linker_env" (LinkerEnv). Verifies both
    files exist and the metadata's search_backend stamp matches the requested
    backend, so a stale or wrong-backend bundle fails loudly instead of
    running with the wrong search client baked in.
    """
    resolved = search_backend(backend)
    directory = bundle_dir(resolved)
    pkl_path = directory / f"{stem}_cls.pkl"
    meta_path = directory / f"{stem}_metadata.json"

    hint = _REBUILD_HINT.format(backend=resolved)
    for path in (pkl_path, meta_path):
        if not path.exists():
            raise FileNotFoundError(f"Missing bundle file {path}. {hint}")

    stamped = json.loads(meta_path.read_text()).get("search_backend")
    if stamped != resolved:
        raise ValueError(
            f"Bundle {pkl_path} is stamped search_backend={stamped!r} but "
            f"backend {resolved!r} was requested. {hint}"
        )
    return pkl_path, meta_path
