from collections import defaultdict
from typing import Any, Dict, Type

from pydantic import ValidationError
from sqlmodel import SQLModel


def parse_json_into_tables(
    json_data: dict, table_models: dict[str, Type[SQLModel]]
) -> Any:
    """ """

    tables = defaultdict(list)
    errors = []
    # Sort models by the number of fields in descending order
    # Bigger model likely to be root model
    # Calculate this once. So pull out and inject into the function.
    sorted_models = sorted(
        table_models.items(), key=lambda x: len(x[1].model_fields), reverse=True
    )

    # Include both field names AND aliases for pre-filter
    model_fields = {}
    for name, cls in table_models.items():
        field_set = set(cls.model_fields.keys())
        for field_info in cls.model_fields.values():
            if field_info.alias:
                field_set.add(field_info.alias)
        model_fields[name] = field_set

    def normalize_path(path: str) -> str:
        if "[" in path:
            # Split the path into segments Ex. ["root", "invoice_items[0]", "id"]]
            segments = path.split(".")
            for index, segment in enumerate(segments):
                # Ex. "invoice_items[0]"
                if "[" in segment:
                    # Replace segment
                    segments[index] = segment.split("[")[0] + "[*]"
            # Rejoin the split segments to form the flattened path
            return ".".join(segments)
        return path

    def extract(json_path: Dict[str, Any], context: Dict[str, Any], path: str) -> None:
        """
        1. Flatten the context (not applicable on first iteration)
        """

        # Normalize context (ancestors)
        flat_context = {normalize_path(k): v for k, v in context.items()}

        # Fix path prefix - NO double root
        base_path = path if path.startswith("root") else f"root.{path}"
        raw_prefixed = {f"{base_path}.{k}": v for k, v in json_path.items()}
        prefixed_json_path = {normalize_path(k): v for k, v in raw_prefixed.items()}

        print(f"\n=== PATH: {path} ===")
        print(f"prefixed_json: {list(prefixed_json_path.keys())}")
        print(f"context: {list(flat_context.keys())}")

        for model_name, model_cls in sorted_models:
            required_fields = model_fields[model_name]
            # If no fields match at all, skip model
            if not any(
                f in prefixed_json_path or f in flat_context for f in required_fields
            ):
                continue

            try:
                validation_data = {
                    # Include json_path fields
                    **prefixed_json_path,
                    # Include flattened parent fields that are not in json_path
                    **{
                        k: v
                        for k, v in flat_context.items()
                        if k not in prefixed_json_path
                    },
                }
                # Validate and append to tables
                tables[model_name].append(
                    model_cls.model_validate(validation_data).model_dump()
                )
            except ValidationError as e:
                errors.append(
                    {
                        "path": path,
                        "model": model_name,
                        "errors": e.errors(),
                    }
                )

    def walk(
        json_obj: Dict[str, Any], context: Dict[str, Any] = {}, path: str = "root"
    ) -> None:
        """
        Recursively walk the JSON object and extract the models.
        1. Extract the root model
        2. For each key, value pair:
            - Create flattened parent paths if not root
            - Add to the context
            - If value is a dict, walk the dict for all the fields
            - If value is a list, walk the list for all the items
            - For each item, grab all the fields
            - Create new path as multiple to reference parent in loop
            - Add to the context
            - Walk the new context and path
        """

        # Extend the context with the current json_obj
        full_context = context.copy()
        for key, value in json_obj.items():
            new_path = f"root.{key}" if path == "root" else f"{path}.{key}"
            full_context[new_path] = value

        # Extract the root model or recursive path if not root
        extract(json_obj, context, path)

        for key, value in json_obj.items():
            # Create flattened parent paths if not root
            new_path = f"root.{key}" if path == "root" else f"{path}.{key}"
            # Add to the context
            new_context = {**context, new_path: value}

            # If value is a dict, walk the dict for all the fields
            if isinstance(value, dict):
                walk(value, new_context, new_path)
            # If value is a list, walk the list for all the items
            elif isinstance(value, list) and value:
                # For each item, grab all the fields
                for index, obj in enumerate(value):
                    if isinstance(obj, dict):
                        # Create new path with positional index
                        list_path = f"{new_path}[{index}]"
                        # Add to the context
                        list_context = {**new_context, list_path: obj}
                        walk(obj, list_context, list_path)

    # Walk the JSON data
    walk(json_data)
    return tables, errors
