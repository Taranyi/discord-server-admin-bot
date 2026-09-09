from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any, Literal, cast

import yaml

from .config import ConfigError

ChannelType = Literal["text", "forum", "voice"]
_CHANNEL_TYPES = {"text", "forum", "voice"}
_ALLOWED_PLACEHOLDERS = {"course_name", "course_code", "semester"}


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConfigError(f"Duplicate configuration key: {key!r}.")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


@dataclass(frozen=True, slots=True)
class ChannelTemplate:
    key: str
    type: ChannelType
    name: str
    topic: str | None = None
    tags: tuple[str, ...] = ()

    def render_name(self, context: dict[str, str]) -> str:
        return self.name.format_map(context)

    def render_topic(self, context: dict[str, str]) -> str | None:
        return self.topic.format_map(context) if self.topic is not None else None


@dataclass(frozen=True, slots=True)
class CourseTemplate:
    category_name: str
    channels: tuple[ChannelTemplate, ...]

    @property
    def requires_community(self) -> bool:
        return any(channel.type == "forum" for channel in self.channels)

    def render_category_name(self, context: dict[str, str]) -> str:
        return self.category_name.format_map(context)


def load_course_template(path: Path) -> CourseTemplate:
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except OSError as error:
        raise ConfigError(f"Cannot read configuration file {path}: {error}.") from error
    except yaml.YAMLError as error:
        raise ConfigError(f"Invalid YAML in {path}: {error}.") from error

    root = _mapping(raw, "configuration root")
    if root.get("schema_version") != 1:
        raise ConfigError("config.yaml schema_version must be 1.")

    template = _mapping(root.get("course_template"), "course_template")
    category = _mapping(template.get("category"), "course_template.category")
    category_name = _required_string(category, "name", "course_template.category")
    _validate_format(category_name, "course_template.category.name")

    raw_channels = _mapping(template.get("channels"), "course_template.channels")
    if not raw_channels:
        raise ConfigError("course_template.channels must not be empty.")

    channels: list[ChannelTemplate] = []
    visible_names: set[str] = set()
    for key, value in raw_channels.items():
        if not isinstance(key, str) or not key.strip():
            raise ConfigError("Every channel template key must be a non-empty string.")
        location = f"course_template.channels.{key}"
        channel = _mapping(value, location)
        raw_type = _required_string(channel, "type", location).lower()
        if raw_type not in _CHANNEL_TYPES:
            raise ConfigError(f"{location}.type must be text, forum, or voice.")
        channel_type = cast(ChannelType, raw_type)
        name = _required_string(channel, "name", location)
        _validate_format(name, f"{location}.name")
        normalized_visible_name = name.casefold()
        if normalized_visible_name in visible_names:
            raise ConfigError(f"Duplicate visible channel name template: {name!r}.")
        visible_names.add(normalized_visible_name)

        topic = channel.get("topic")
        if topic is not None and not isinstance(topic, str):
            raise ConfigError(f"{location}.topic must be a string.")
        if topic is not None:
            _validate_format(topic, f"{location}.topic")

        tags = _parse_tags(channel.get("tags", []), location, channel_type)
        channels.append(
            ChannelTemplate(
                key=key,
                type=channel_type,
                name=name,
                topic=topic,
                tags=tags,
            )
        )

    return CourseTemplate(category_name=category_name, channels=tuple(channels))


def _mapping(value: object, location: str) -> dict[Any, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{location} must be a mapping.")
    return value


def _required_string(mapping: dict[Any, Any], key: str, location: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{location}.{key} must be a non-empty string.")
    return value.strip()


def _validate_format(value: str, location: str) -> None:
    try:
        fields = {field for _, field, _, _ in Formatter().parse(value) if field}
    except ValueError as error:
        raise ConfigError(f"Invalid placeholder syntax in {location}.") from error
    unknown = fields - _ALLOWED_PLACEHOLDERS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigError(f"Unsupported placeholder(s) in {location}: {names}.")


def _parse_tags(
    value: object, location: str, channel_type: ChannelType
) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(tag, str) for tag in value):
        raise ConfigError(f"{location}.tags must be a list of strings.")
    tags = tuple(tag.strip() for tag in value)
    if any(not tag or len(tag) > 20 for tag in tags):
        raise ConfigError(f"Every {location}.tags item must contain 1-20 characters.")
    if len(tags) > 20:
        raise ConfigError(f"{location}.tags supports at most 20 tags.")
    if len({tag.casefold() for tag in tags}) != len(tags):
        raise ConfigError(f"{location}.tags contains duplicate values.")
    if tags and channel_type != "forum":
        raise ConfigError(f"Only forum channels may define {location}.tags.")
    return tags
