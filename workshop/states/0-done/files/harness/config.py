"""Settings, read from environment variables (SPEC 3.1)."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    db_path: Path
    model_provider: str
    model_name: str
    script_path: Path | None


def load_config() -> Config:
    """Read the environment afresh on every call. An empty variable counts as unset."""
    script = os.environ.get("HARNESS_SCRIPT")
    return Config(
        db_path=Path(os.environ.get("HARNESS_DB") or "my/var/harness.db"),
        model_provider=os.environ.get("HARNESS_MODEL_PROVIDER") or "auto",  # picked when a model is asked for (3.7)
        model_name=os.environ.get("HARNESS_MODEL") or "claude-sonnet-5-5",
        script_path=Path(script) if script else None,
    )
