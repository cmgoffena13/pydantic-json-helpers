import re
from dataclasses import dataclass
from typing import Any, Dict, List, Type

from pydantic import BaseModel, ValidationError


@dataclass
class ModelSpec:
    model_cls: Type[BaseModel]
    path_pattern: str  # "root.invoice_items[*]"
    parent_pattern: str | None = None  # "root" for FK resolution


# Cache compiled regex patterns (pattern -> compiled regex)
_pattern_cache: Dict[str, re.Pattern] = {}
# Compiled regex for extracting array indices like [0], [1], etc.
_index_pattern = re.compile(r"\[(\d+)\]")


def path_matches(path: str, pattern: str) -> bool:
    """Check if path matches pattern, with cached compiled regex"""
    if pattern not in _pattern_cache:
        escaped = re.escape(pattern).replace(r"\[\*\]", r"\[\d+\]")
        _pattern_cache[pattern] = re.compile(escaped)
    return bool(_pattern_cache[pattern].fullmatch(path))


def resolve_alias_with_wildcards(alias_path: str, current_path: str) -> str:
    """Replace [*] in alias with actual indices from current_path by matching path segments"""
    # Split both paths into segments
    alias_segments = alias_path.split(".")
    current_segments = current_path.split(".")

    resolved_segments = []
    current_idx = 0

    for alias_seg in alias_segments:
        if "[*]" in alias_seg:
            # Find the matching segment in current_path
            key_name = alias_seg.split("[")[0]
            # Look for matching key in current_path segments
            while current_idx < len(current_segments):
                current_seg = current_segments[current_idx]
                if current_seg.startswith(key_name + "["):
                    # Extract the index from current segment
                    match = _index_pattern.search(current_seg)
                    if match:
                        idx = match.group(1)
                        resolved_segments.append(f"{key_name}[{idx}]")
                        current_idx += 1
                        break
                current_idx += 1
            else:
                # No match found, keep [*] (shouldn't happen in valid cases)
                resolved_segments.append(alias_seg)
        else:
            resolved_segments.append(alias_seg)
            # Advance current_idx if this segment matches
            if (
                current_idx < len(current_segments)
                and current_segments[current_idx] == alias_seg
            ):
                current_idx += 1

    return ".".join(resolved_segments)


def _build_model_data(
    obj: Dict[str, Any],
    path: str,
    spec: ModelSpec,
    path_index: Dict[str, Any],
) -> Dict[str, Any]:
    """Build model data using cached path index instead of traversing JSON"""
    data = {}

    for field_name, field_info in spec.model_cls.model_fields.items():
        alias = field_info.alias

        if alias == field_name or alias is None:
            data[field_name] = obj.get(field_name)
        else:
            resolved_alias = resolve_alias_with_wildcards(alias, path)
            data[field_name] = path_index.get(resolved_alias)

    return data


def _index_path(obj: Any, path: str, path_index: Dict[str, Any]) -> None:
    """Build path index by recursively indexing all paths and values"""
    path_index[path] = obj

    if isinstance(obj, dict):
        # Index individual scalar fields for quick lookup
        for key, value in obj.items():
            field_path = f"{path}.{key}"
            path_index[field_path] = value
            # Recurse into nested structures
            if isinstance(value, (dict, list)):
                _index_path(value, field_path, path_index)
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            item_path = f"{path}[{index}]"
            path_index[item_path] = item
            if isinstance(item, (dict, list)):
                _index_path(item, item_path, path_index)


def _extract_models_at_path(
    obj: Dict[str, Any],
    path: str,
    specs: List[ModelSpec],
    path_index: Dict[str, Any],
    results: Dict[str, List[Dict[str, Any]]],
    errors: List[Dict[str, Any]],
) -> None:
    for spec in specs:
        if path_matches(path, spec.path_pattern):
            try:
                data = _build_model_data(obj, path, spec, path_index)
                results[spec.path_pattern].append(
                    spec.model_cls.model_validate(data).model_dump()
                )
            except ValidationError as e:
                errors.append(
                    {
                        "path": path,
                        "model": spec.path_pattern,
                        "errors": e.errors(),
                    }
                )


def extract_model_data(
    json_obj: Any, specs: List[ModelSpec]
) -> tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    results = {spec.path_pattern: [] for spec in specs}
    errors = []
    path_index = {}

    def walk(obj: Any, path: str = "root"):
        path_index[path] = obj

        if isinstance(obj, dict):
            for key, value in obj.items():
                field_path = f"{path}.{key}"
                path_index[field_path] = value
                if isinstance(value, (dict, list)):
                    walk(value, field_path)

            _extract_models_at_path(obj, path, specs, path_index, results, errors)

        elif isinstance(obj, list):
            for index, item in enumerate(obj):
                item_path = f"{path}[{index}]"
                path_index[item_path] = item
                if isinstance(item, (dict, list)):
                    walk(item, item_path)

    walk(json_obj)
    return results, errors
