import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Type

from pydantic import BaseModel, TypeAdapter, ValidationError


@dataclass
class ModelSpec:
    data_model: Type[BaseModel]
    json_path_pattern: str  # "root.invoice_items[*]"


class TableBatch:
    def __init__(self, stage_table_name, data_model):
        self.stage_table_name = stage_table_name
        self.data_model = data_model
        self.records = []
        self.errors = []

    def add_error(self, error: dict):
        self.errors.append(error)

    def add_record(self, record: dict):
        self.records.append(record)


class JSONParser:
    def __init__(self, data_models: list[Type[BaseModel]]):
        self.model_specs = {}
        self.model_adapters = {}
        self.results = defaultdict(list)
        self.errors = []
        self.indexed_cache = {}
        self.regex_pattern_cache = {}
        self.model_fields_cache = {}
        self.index_pattern = re.compile(r"\[(\d+)\]")
        self._model_specs_create_specs_and_adapters(data_models)

    def clear_index_cache(self):
        self.indexed_cache = {}

    def clear_batch_results(self):
        self.results = defaultdict(list)

    def _model_specs_find_deepest_common_path_pattern(self, aliases: list[str]) -> str:
        paths = [".".join(alias.split(".")[:-1]) for alias in aliases]
        path_segments = [path.split(".") for path in paths]
        common_segments = []
        min_length = min(len(segments) for segments in path_segments)

        for index in range(min_length):
            segments_at_position = [segments[index] for segments in path_segments]
            first_segment = segments_at_position[0]
            first_base = (
                first_segment.split("[")[0] if "[" in first_segment else first_segment
            )

            if all(
                seg.split("[")[0] == first_base if "[" in seg else seg == first_base
                for seg in segments_at_position
            ):
                common_segments.append(first_segment)
            else:
                break

        return ".".join(common_segments) if common_segments else "root"

    def _model_specs_create_specs_and_adapters(
        self, data_models: list[Type[BaseModel]]
    ) -> None:
        for model_cls in data_models:
            all_aliases = []
            fields = []

            for field_name, field_info in model_cls.model_fields.items():
                alias = field_info.alias
                if alias is None:
                    raise ValueError(f"Alias is required for field {field_name}")

                has_wildcard = "[*]" in alias
                fields.append((field_name, alias, has_wildcard))
                all_aliases.append(alias)

            model_name = model_cls.__name__
            self.model_fields_cache[model_name] = fields

            wildcard_aliases = [
                alias for _, alias, has_wildcard in fields if has_wildcard
            ]
            if wildcard_aliases:
                json_path_pattern = self._model_specs_find_deepest_wildcard_path(
                    wildcard_aliases
                )
            else:
                json_path_pattern = self._model_specs_find_deepest_common_path_pattern(
                    all_aliases
                )

            spec = ModelSpec(
                data_model=model_cls,
                json_path_pattern=json_path_pattern,
            )

            self.model_specs[model_name] = spec
            self.model_adapters[model_name] = TypeAdapter(model_cls)

    def _model_specs_find_deepest_wildcard_path(self, aliases: list[str]) -> str:
        return max(
            (".".join(alias.split(".")[:-1]) for alias in aliases),
            key=lambda p: p.count("."),
        )

    def _parsing_path_matches(self, path: str, pattern: str) -> bool:
        if pattern not in self.regex_pattern_cache:
            escaped = re.escape(pattern).replace(r"\[\*\]", r"\[\d+\]")
            self.regex_pattern_cache[pattern] = re.compile(escaped)
        return bool(self.regex_pattern_cache[pattern].fullmatch(path))

    def _parsing_replace_wildcard_with_index(
        self, alias_path: str, current_path: str
    ) -> str:
        alias_segments = alias_path.split(".")
        current_segments = current_path.split(".")
        resolved_segments = []
        current_index = 0

        for alias_segment in alias_segments:
            if "[*]" in alias_segment:
                key_name = alias_segment.split("[")[0]
                found = False
                for index in range(current_index, len(current_segments)):
                    seg = current_segments[index]
                    if seg.startswith(key_name + "["):
                        match = self.index_pattern.search(seg)
                        if match:
                            resolved_segments.append(f"{key_name}[{match.group(1)}]")
                            current_index = index + 1
                            found = True
                            break
                if not found:
                    resolved_segments.append(alias_segment)
            else:
                resolved_segments.append(alias_segment)
                if (
                    current_index < len(current_segments)
                    and current_segments[current_index] == alias_segment
                ):
                    current_index += 1

        return ".".join(resolved_segments)

    def _parsing_build_model_data(self, path: str, spec: ModelSpec) -> dict:
        data = {}
        model_name = spec.data_model.__name__
        for field_name, alias, has_wildcard in self.model_fields_cache[model_name]:
            if has_wildcard:
                resolved_alias = self._parsing_replace_wildcard_with_index(alias, path)
            else:
                resolved_alias = alias
            data[field_name] = self.indexed_cache.get(resolved_alias)
        return data

    def _parsing_extract_models_at_path(self, path: str) -> None:
        for model_name, spec in self.model_specs.items():
            if self._parsing_path_matches(path, spec.json_path_pattern):
                try:
                    data = self._parsing_build_model_data(path, spec)
                    adapter = self.model_adapters[model_name]
                    self.results[model_name].append(
                        adapter.validate_python(data).model_dump()
                    )
                except ValidationError as e:
                    self.errors.append(
                        {
                            "path": path,
                            "model": model_name,
                            "errors": e.errors(),
                        }
                    )

    def _parsing_walk(self, obj: Any, path: str = "root"):
        self.indexed_cache[path] = obj

        if isinstance(obj, dict):
            for key, value in obj.items():
                field_path = f"{path}.{key}"
                self.indexed_cache[field_path] = value
                if isinstance(value, (dict, list)):
                    self._parsing_walk(value, field_path)

            self._parsing_extract_models_at_path(path)

        elif isinstance(obj, list):
            for index, item in enumerate(obj):
                item_path = f"{path}[{index}]"
                self.indexed_cache[item_path] = item
                if isinstance(item, (dict, list)):
                    self._parsing_walk(item, item_path)

    def parse(self, json_obj: dict):
        self.clear_index_cache()
        self.results = {model_name: [] for model_name in self.model_specs.keys()}
        self._parsing_walk(json_obj)
        if self.errors:
            raise ValueError(self.errors)
        return self.results

    def parse_batch(self, json_objs: list[dict]):
        self.clear_batch_results()
        self.results = {model_name: [] for model_name in self.model_specs.keys()}
        for json_obj in json_objs:
            self._parsing_walk(json_obj)
        return self.results
