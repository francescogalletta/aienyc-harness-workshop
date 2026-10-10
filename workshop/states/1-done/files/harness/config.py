"""Settings, read from environment variables (SPEC 3.1, 4.1 and 4.8)."""
import os
from dataclasses import dataclass
from pathlib import Path

EXAMPLES_DIR = Path("examples")     # the seeded examples (SPEC 6.1)
EXAMPLE_COPIES = Path("my/var/examples")    # example mode works on a copy here (SPEC 4.8)
UNKNOWN_EXAMPLE = "There is no example called '{name}'. The examples are: {names}."


@dataclass(frozen=True)
class Config:
    db_path: Path
    model_provider: str
    model_name: str
    script_path: Path | None
    researcher: str             # step 1: who looks up standard definitions
    reference_path: Path        # step 1: the saved reference file
    brief_dir: Path             # step 1: where the domain brief is written
    example: str | None = None  # step 1: play with examples/<name>/ (4.8)


def load_config() -> Config:
    """Read the environment afresh on every call. An empty variable counts as unset."""
    script = os.environ.get("HARNESS_SCRIPT")
    example = os.environ.get("HARNESS_EXAMPLE") or None
    # With an example, the defaults move to a copy of it; a variable set explicitly still wins (4.8).
    db_default = f"{EXAMPLE_COPIES}/{example}/harness.db" if example else "my/var/harness.db"
    brief_default = f"{EXAMPLE_COPIES}/{example}/brief" if example else "my/brief"
    return Config(
        db_path=Path(os.environ.get("HARNESS_DB") or db_default),
        model_provider=os.environ.get("HARNESS_MODEL_PROVIDER") or "auto",  # picked when a model is asked for (3.7)
        model_name=os.environ.get("HARNESS_MODEL") or "claude-sonnet-5-5",
        script_path=Path(script) if script else None,
        researcher=os.environ.get("HARNESS_RESEARCHER") or "auto",
        reference_path=Path(os.environ.get("HARNESS_REFERENCE") or "reference/terms.json"),
        brief_dir=Path(os.environ.get("HARNESS_BRIEF_DIR") or brief_default),
        example=example,
    )
