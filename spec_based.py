import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Type

from pydantic import BaseModel, ValidationError


@dataclass
class ModelSpec:
    model_cls: Type[BaseModel]
    path_pattern: str  # "root.invoice_items[*]"
    parent_pattern: str | None = None  # "root" for FK resolution


def infer_model_specs(table_models: Dict[str, Type[BaseModel]]) -> List[ModelSpec]:
    """
    Automatically infer ModelSpecs from model field aliases.

    Analyzes each model's field aliases to determine:
    - path_pattern: Uses the primary key field's alias (most specific path)
    - parent_pattern: Inferred from foreign key field aliases
    """
    specs = []

    for model_name, model_cls in table_models.items():
        # Find primary key field (usually has primary_key=True or is named 'id')
        pk_alias = None
        all_aliases = []
        fk_aliases = []  # Foreign key aliases (for parent pattern inference)

        for field_name, field_info in model_cls.model_fields.items():
            alias = field_info.alias
            if alias and alias != field_name:
                all_aliases.append(alias)

                # Check if this is a primary key
                is_pk = (
                    field_name == "id"
                    or field_name.endswith("_id")
                    and hasattr(field_info, "json_schema_extra")
                    and field_info.json_schema_extra
                    and field_info.json_schema_extra.get("primary_key")
                ) or (
                    # Check Field() constraints for primary_key
                    hasattr(field_info, "constraints")
                    and any(
                        "primary_key" in str(c) for c in (field_info.constraints or [])
                    )
                )

                if is_pk or (not pk_alias and field_name in ("id", "tx_id")):
                    pk_alias = alias

                # Check if this is a foreign key (heuristic: field ends with _id but not primary)
                if field_name.endswith("_id") and alias and not is_pk:
                    fk_aliases.append(alias)

        # Use primary key alias as path pattern, or find deepest common path
        if pk_alias:
            # Extract path up to the field (remove the field name at the end)
            path_segments = pk_alias.split(".")
            # Remove the last segment (the field name) to get the path pattern
            path_pattern = (
                ".".join(path_segments[:-1]) if len(path_segments) > 1 else "root"
            )
        elif all_aliases:
            # Fallback: find deepest common path
            path_pattern = _find_deepest_common_path(all_aliases)
        else:
            path_pattern = "root"

        # Infer parent pattern from FK aliases
        parent_pattern = None
        if fk_aliases:
            # Use the shallowest FK alias (closest parent)
            parent_pattern = _find_shallowest_path(fk_aliases)
            # If parent is same as current, try to go one level up
            if parent_pattern == path_pattern:
                parent_pattern = _get_parent_path(path_pattern)

        specs.append(ModelSpec(model_cls, path_pattern, parent_pattern))

    return specs


def _find_deepest_common_path(aliases: List[str]) -> str:
    """Find the deepest common path that matches most aliases"""
    if not aliases:
        return "root"

    # Group aliases by their path depth
    paths_by_depth = {}
    for alias in aliases:
        path = ".".join(alias.split(".")[:-1])  # Remove field name
        depth = path.count(".")
        if depth not in paths_by_depth:
            paths_by_depth[depth] = []
        paths_by_depth[depth].append(path)

    # Start from deepest and work up
    for depth in sorted(paths_by_depth.keys(), reverse=True):
        paths = paths_by_depth[depth]
        common = _find_common_path_pattern(paths)
        if common and common != "root":
            return common

    return "root"


def _find_shallowest_path(aliases: List[str]) -> str:
    """Find the shallowest (shortest) path from aliases"""
    if not aliases:
        return "root"

    paths = [".".join(alias.split(".")[:-1]) for alias in aliases]  # Remove field names
    # Return the shortest path
    return min(paths, key=lambda p: p.count(".")) if paths else "root"


def _find_common_path_pattern(aliases: List[str]) -> str:
    """Find the common path pattern from a list of alias paths"""
    if not aliases:
        return "root"

    # Split all aliases into segments
    alias_segments = [alias.split(".") for alias in aliases]

    # Find common prefix segments
    common_segments = []
    min_length = min(len(segments) for segments in alias_segments)

    for i in range(min_length):
        # Get all segments at this position
        segments_at_pos = [segments[i] for segments in alias_segments]

        # Check if all segments match (accounting for [*] wildcards)
        first_seg = segments_at_pos[0]

        # Extract base key name (without index)
        first_base = first_seg.split("[")[0] if "[" in first_seg else first_seg

        # Check if all segments have the same base key
        all_match = all(
            seg.split("[")[0] == first_base if "[" in seg else seg == first_base
            for seg in segments_at_pos
        )

        if all_match:
            # Use the first segment (preserves [*] if present)
            common_segments.append(first_seg)
        else:
            # Stop at first non-matching segment
            break

    return ".".join(common_segments) if common_segments else "root"


def _get_parent_path(path: str) -> str | None:
    """Get parent path by removing the last segment"""
    segments = path.split(".")
    if len(segments) <= 1:
        return None
    return ".".join(segments[:-1])


def path_matches(path: str, pattern: str) -> bool:
    """Check if actual path matches pattern (with [*] wildcards)"""
    # Escape pattern and convert [*] to regex
    escaped = re.escape(pattern).replace(r"\[\*\]", r"\[\d+\]")
    return bool(re.fullmatch(escaped, path))


def _get_value_from_path(obj: Dict[str, Any], path: str) -> Any:
    """Extract value from nested dict using dot notation path"""
    parts = path.split(".")
    current = obj
    for part in parts:
        if "[" in part:
            # Handle array access like "invoice_items[0]"
            key, index_str = part.split("[", 1)
            index_str = index_str.rstrip("]")

            # Handle [*] wildcard - shouldn't happen after resolution, but handle gracefully
            if index_str == "*":
                return None  # Can't resolve wildcard without context

            try:
                index = int(index_str)
            except ValueError:
                return None  # Invalid index format

            if isinstance(current, dict) and key in current:
                current = current[key]
                if isinstance(current, list) and 0 <= index < len(current):
                    current = current[index]
                else:
                    return None
            else:
                return None
        else:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
    return current


def _build_model_data(
    obj: Dict[str, Any],
    path: str,
    spec: ModelSpec,
    root_json: Dict[str, Any],
    resolve_wildcards: Callable[[str, str], str],
) -> Dict[str, Any]:
    """Resolve ALL field aliases using root JSON structure"""
    data = {}

    for field_name, field_info in spec.model_cls.model_fields.items():
        alias = field_info.alias

        if alias == field_name or alias is None:
            # Local field - get from current object
            data[field_name] = obj.get(field_name)
        else:
            # Resolve alias path from root JSON
            # Replace [*] wildcards with actual indices from current path
            resolved_alias = resolve_wildcards(alias, path)
            # Extract value from root using resolved path
            data[field_name] = _get_value_from_path(
                root_json, resolved_alias.replace("root.", "")
            )

    return data


def extract_model_data(
    json_obj: Any, specs: List[ModelSpec]
) -> tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """Single recursive pass with parent context tracking"""
    results = {spec.path_pattern: [] for spec in specs}
    errors = []
    root_json = json_obj  # Keep reference to root for absolute path resolution

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
                        match = re.search(r"\[(\d+)\]", current_seg)
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

    def recurse(obj: Any, path: str = "root"):
        if isinstance(obj, dict):
            # Check all specs
            for spec in specs:
                if path_matches(path, spec.path_pattern):
                    try:
                        # Build data + inject parent FKs
                        data = _build_model_data(
                            obj, path, spec, root_json, resolve_alias_with_wildcards
                        )
                        # Validate the data matches the model
                        validated = spec.model_cls.model_validate(data)
                        results[spec.path_pattern].append(validated.model_dump())
                    except ValidationError as e:
                        errors.append(
                            {
                                "path": path,
                                "model": spec.path_pattern,
                                "errors": e.errors(),
                            }
                        )

            # Recurse
            for key, value in obj.items():
                recurse(value, f"{path}.{key}")

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                recurse(item, f"{path}[{i}]")

    recurse(json_obj)
    return results, errors
