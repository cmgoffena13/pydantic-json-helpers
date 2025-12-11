from typing import Any, Dict

from json_examples.nestedjson import NESTED_JSON


def walk_json(
    json_obj: Any, context: Dict[str, Any] | None = None, path: str = "root"
) -> None:
    if context is None:
        context = {}

    if isinstance(json_obj, dict):
        for key, value in json_obj.items():
            new_path = f"{path}.{key}"
            if isinstance(value, (dict, list)):
                walk_json(value, context, new_path)
            else:
                print(f"{new_path} = {value}")

    elif isinstance(json_obj, list):
        for index, item in enumerate(json_obj):
            new_path = f"{path}[{index}]"
            if isinstance(item, (dict, list)):
                walk_json(item, context, new_path)
            else:
                print(f"{new_path} = {item}")


walk_json(NESTED_JSON)
