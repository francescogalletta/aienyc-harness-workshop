"""Settings, read from environment variables (SPEC 2.1)."""
import os
from dataclasses import dataclass
from pathlib import Path

EXAMPLES_DIR = Path("examples")     # the seeded examples
EXAMPLE_COPIES = Path("my/var/examples")    # example mode works on a copy here
UNKNOWN_EXAMPLE = "There is no example called '{name}'. The examples are: {names}."
LAYERS_FILE = Path("my/var/layers")     # a local default for HARNESS_LAYERS: one whole number (ARCHITECTURE.md section 7)
MAX_LAYER = 5
BAD_LAYERS_FILE = "{path} must hold one whole number from 0 to 5, not {value!r}. Delete it to run all five layers."
BAD_LAYERS = "HARNESS_LAYERS must be a whole number from 0 to 5, not {value!r}."
BAD_REVIEW = "HARNESS_REVIEW must be auto or off, not {value!r}."


@dataclass(frozen=True)
class Config:
    db_path: Path
    model_provider: str
    model_name: str
    script_path: Path | None
    researcher: str             # layer 1: who looks up standard definitions
    reference_path: Path        # layer 1: the saved reference file
    brief_dir: Path             # layer 1: where the domain brief is written
    modules_dir: Path           # layer 2: where the module folders live
    example: str | None = None  # play with examples/<name>/
    layers: int = MAX_LAYER     # layers above this are off (ARCHITECTURE.md section 7)
    review: str = "auto"        # layer 5: "off" means no automatic review passes


def _layers(value: str | None) -> int:
    if value is None:
        return MAX_LAYER
    text = value.strip()
    if not (text.isascii() and text.isdigit()) or not 0 <= int(text) <= MAX_LAYER:
        raise ValueError(BAD_LAYERS.format(value=value))
    return int(text)


def _layers_from_file(path: Path = LAYERS_FILE) -> int | None:
    """The local default: the number in `my/var/layers`, or None when there is no such file."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
        raise ValueError(BAD_LAYERS_FILE.format(path=path, value="(unreadable)")) from None
    if not (text.isascii() and text.isdigit()) or not 0 <= int(text) <= MAX_LAYER:
        raise ValueError(BAD_LAYERS_FILE.format(path=path, value=text))
    return int(text)


def _layers_setting(value: str | None) -> int:
    """HARNESS_LAYERS wins; else the local file; else all five."""
    if value is not None:
        return _layers(value)
    from_file = _layers_from_file()
    return MAX_LAYER if from_file is None else from_file


def _review(value: str | None) -> str:
    if value is None:
        return "auto"
    if value.strip() not in ("auto", "off"):
        raise ValueError(BAD_REVIEW.format(value=value))
    return value.strip()


def load_config() -> Config:
    """Read the environment afresh on every call. An empty variable counts as unset.

    A bad HARNESS_LAYERS or HARNESS_REVIEW raises ValueError, naming the variable.
    """
    def get(name):
        return os.environ.get(name) or None

    script = get("HARNESS_SCRIPT")
    example = get("HARNESS_EXAMPLE")
    # With an example, the defaults move to a copy of it; a variable set explicitly still wins.
    db_default = f"{EXAMPLE_COPIES}/{example}/harness.db" if example else "my/var/harness.db"
    brief_default = f"{EXAMPLE_COPIES}/{example}/brief" if example else "my/brief"
    modules_default = f"{EXAMPLE_COPIES}/{example}/modules" if example else "my/modules"
    return Config(
        db_path=Path(get("HARNESS_DB") or db_default),
        model_provider=get("HARNESS_MODEL_PROVIDER") or "auto",
        model_name=get("HARNESS_MODEL") or "claude-sonnet-5-5",
        script_path=Path(script) if script else None,
        researcher=get("HARNESS_RESEARCHER") or "auto",
        reference_path=Path(get("HARNESS_REFERENCE") or "reference/terms.json"),
        brief_dir=Path(get("HARNESS_BRIEF_DIR") or brief_default),
        modules_dir=Path(get("HARNESS_MODULES_DIR") or modules_default),
        example=example,
        layers=_layers_setting(get("HARNESS_LAYERS")),
        review=_review(get("HARNESS_REVIEW")),
    )
