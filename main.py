from collections import defaultdict
from typing import Any, Dict, List, Type

from pydantic import ValidationError
from sqlmodel import SQLModel


def parse_json_to_tables(
    root_json: Dict[str, Any] | List[Dict[str, Any]],
    table_models: Dict[str, Type[SQLModel]],
) -> tuple[Dict[str, List[SQLModel]], List[Dict[str, Any]]]:
    tables = defaultdict(list)
    errors = []
    sorted_models = sorted(
        table_models.items(), key=lambda x: len(x[1].model_fields), reverse=True
    )

    model_fields = {
        name: set(cls.model_fields.keys()) for name, cls in table_models.items()
    }

    def flatten_context(context: Dict[str, Any]) -> Dict[str, Any]:
        """invoice_items[0].id → invoice_items[*].id"""
        flat = {}
        for path, value in context.items():
            if "[" in path:
                segments = path.split(".")
                # Find array segment: invoice_items[0]
                for i, seg in enumerate(segments):
                    if "[" in seg:
                        # Replace [0] → [*]
                        segments[i] = seg.replace(
                            f"[{seg.split('[')[1].split(']')[0]}]", "[*]"
                        )
                        break
                prefix = ".".join(segments)
                field_name = segments[-1]
                flat[f"{prefix}.{field_name}"] = value
            else:
                field_name = path.split(".")[-1]
                flat[field_name] = value
        return flat

    def extract(json_path: Dict[str, Any], context: Dict[str, Any], path: str) -> None:
        flat_context = flatten_context(context)

        for model_name, model_cls in sorted_models:
            required_fields = model_fields[model_name]
            if not any(f in json_path or f in flat_context for f in required_fields):
                continue

            try:
                validation_data = {
                    **json_path,
                    **{k: v for k, v in flat_context.items() if k not in json_path},
                }
                tables[model_name].append(model_cls.model_validate(validation_data))
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
    ):
        extract(json_obj, context, path)

        for key, value in json_obj.items():
            new_path = f"{path}.{key}" if path != "root" else key
            new_context = {**context, new_path: value}

            if isinstance(value, dict):
                walk(value, new_context, new_path)
            elif isinstance(value, list) and value:
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        list_path = f"{new_path}[{i}]"
                        walk(item, {**context, list_path: item}, list_path)

    if isinstance(root_json, list):
        for record in root_json:
            walk(record)
    else:
        walk(root_json)

    return dict(tables), errors
