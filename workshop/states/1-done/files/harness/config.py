"""Settings, read from environment variables (SPEC 3.1 and 4.1)."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    db_path: Path
    model_provider: str
    model_name: str
    script_path: Path | None
    researcher: str             # step 1: who looks up standard definitions
    reference_path: Path        # step 1: the saved reference file
    brief_dir: Path             # step 1: where the domain brief is written


def load_config() -> Config:
    """Read the environment afresh on every call. An empty variable counts as unset."""
    script = os.environ.get("HARNESS_SCRIPT")
    return Config(
        db_path=Path(os.environ.get("HARNESS_DB") or "my/var/harness.db"),
        model_provider=os.environ.get("HARNESS_MODEL_PROVIDER") or "auto",  # picked when a model is asked for (3.7)
        model_name=os.environ.get("HARNESS_MODEL") or "claude-sonnet-5-5",
        script_path=Path(script) if script else None,
        researcher=os.environ.get("HARNESS_RESEARCHER") or "auto",
        reference_path=Path(os.environ.get("HARNESS_REFERENCE") or "reference/terms.json"),
        brief_dir=Path(os.environ.get("HARNESS_BRIEF_DIR") or "my/brief"),
    )
