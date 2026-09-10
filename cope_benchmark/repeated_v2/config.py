"""Frozen phase-1 design; loading this module never loads an execution provider."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .canonical import canonical_json

ROOT = Path(__file__).resolve().parents[2]
SPECIFICATION = ROOT / "docs/repeated_v2/specification/02_CONFIG_TEMPLATE.yaml"
SPECIFICATION_V2_1 = ROOT / "docs/repeated_v2/specification/02_CONFIG_TEMPLATE_V2_1.yaml"
SPECIFICATIONS = {
    "repeated_interruptions_v2_config_v1": SPECIFICATION,
    "repeated_interruptions_v2_1_config_v1": SPECIFICATION_V2_1,
}


def _read_yaml(path: Path) -> dict[str, Any]:
    import yaml

    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ValueError("config contains duplicate/non-string key")
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    if not isinstance(value, dict):
        raise ValueError("config must be an object")
    canonical_json(value)
    return value


def validate_config(config: Mapping[str, Any]) -> tuple[str, ...]:
    """Refuse scientific drift. Only the artifact destination may be changed."""
    errors = []
    schema_version = config.get("schema_version") if isinstance(config, Mapping) else None
    specification = SPECIFICATIONS.get(schema_version)
    if specification is None:
        return ("config.schema_version: unsupported frozen scientific config",)
    expected = _read_yaml(specification)

    def compare(actual, required, path):
        if isinstance(required, dict):
            if not isinstance(actual, Mapping):
                errors.append(f"{path}: expected object")
                return
            for key in sorted(set(actual) | set(required)):
                if key not in actual or key not in required:
                    errors.append(f"{path}.{key}: missing or unexpected config field")
                elif path == "config.output" and key == "root":
                    if not isinstance(actual[key], str) or not actual[key].strip():
                        errors.append(f"{path}.{key}: expected nonempty artifact path")
                else:
                    compare(actual[key], required[key], f"{path}.{key}")
        elif canonical_json(actual) != canonical_json(required):
            errors.append(f"{path}: differs from frozen scientific config")

    try:
        canonical_json(config)
        compare(config, expected, "config")
    except (TypeError, ValueError) as exc:
        errors.append(f"invalid config: {exc}")
    return tuple(errors)


def load_config(path: str | Path) -> dict[str, Any]:
    config = _read_yaml(Path(path))
    errors = validate_config(config)
    if errors:
        raise ValueError("INVALID_PROTOCOL_CONFIG: " + "; ".join(errors))
    return config
