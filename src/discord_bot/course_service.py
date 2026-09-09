from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import discord

from .database import (
    BulkChannelDefinition,
    Course,
    Database,
    ManagedChannel,
    ObservedChannel,
    normalize_name,
)
from .template import ChannelTemplate, CourseTemplate


class CourseServiceError(RuntimeError):
    """A course operation that can be explained safely to an administrator."""


class CourseProvisionError(CourseServiceError):
    def __init__(self, message: str, created: list[str]) -> None:
        super().__init__(message)
        self.created = tuple(created)


@dataclass(frozen=True, slots=True)
class CourseCreationResult:
    course: Course
    created: tuple[str, ...]
    resumed: bool


@dataclass(frozen=True, slots=True)
class CourseSyncResult:
    course: Course
    category_name: str | None
    category_issue: str | None
    category_rebound: bool
    present_count: int
    accepted_changes: tuple[str, ...]
    rebound: tuple[str, ...]
    missing: tuple[str, ...]
    ambiguous: tuple[str, ...]
    additional: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BulkChannelAddResult:
    name: str
    channel_type: str
    confirmed: bool
    course_count: int
    create: tuple[str, ...]
    reconnect: tuple[str, ...]
    already_present: tuple[str, ...]
    conflicts: tuple[str, ...]
    created: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BulkChannelDeleteResult:
    definition: BulkChannelDefinition
    confirmed: bool
    live: tuple[str, ...]
    missing: tuple[str, ...]
    deleted: tuple[str, ...]
    failures: tuple[str, ...]
    definition_removed: bool


@dataclass(frozen=True, slots=True)
class CourseDeleteResult:
    course: Course
    confirmed: bool
    managed_live: tuple[str, ...]
    managed_missing: tuple[str, ...]
    manual_kept: tuple[str, ...]
    category_will_delete: bool
    deleted: tuple[str, ...]
    failures: tuple[str, ...]
    record_removed: bool


class CourseService:
    def __init__(self, database: Database, template: CourseTemplate) -> None:
        self.database = database
        self.template = template

    async def create_course(
        self,
        guild: discord.Guild,
        *,
        name: str,
        semester_name: str,
        code: str | None,
        requested_by: int,
    ) -> CourseCreationResult:
        clean_name = clean_entity_name(name, "Course name", 100)
        clean_semester_name = clean_entity_name(semester_name, "Semester name", 100)
        clean_code = clean_optional_code(code)

        self._require_manage_channels(guild)
        bulk_definitions = self.database.list_bulk_channel_definitions(guild.id)
        requires_community = self.template.requires_community or any(
            definition.channel_type == "forum" for definition in bulk_definitions
        )
        if requires_community and "COMMUNITY" not in guild.features:
            raise CourseServiceError(
                "Forum channels require Community to be enabled on this server."
            )

        semester = self.database.get_semester(guild.id, clean_semester_name)
        if semester is None:
            raise CourseServiceError(f'Semester "{clean_semester_name}" does not exist.')

        existing = self.database.get_course(guild.id, clean_name)
        resumed = existing is not None
        if existing is not None and existing.status == "active":
            raise CourseServiceError(f'Course "{existing.name}" already exists.')
        if existing is not None:
            if existing.semester_id != semester.id:
                raise CourseServiceError(
                    "The incomplete course belongs to a different semester."
                )
            if clean_code is not None and clean_code != existing.code:
                raise CourseServiceError(
                    "The incomplete course has a different course code."
                )
            course = existing
            clean_code = existing.code
            clean_name = existing.name
        else:
            initial_context = {
                "course_name": clean_name,
                "course_code": clean_code or "",
                "semester": semester.name,
            }
            initial_category_name = self.template.render_category_name(
                initial_context
            ).strip()
            _validate_rendered_name(initial_category_name, "Course category")
            if any(
                category.name.casefold() == initial_category_name.casefold()
                for category in guild.categories
            ):
                raise CourseServiceError(
                    f'A category named "{initial_category_name}" already exists '
                    "but is not managed."
                )
            course = self.database.begin_course(
                guild.id, semester, clean_name, clean_code
            )
            if course is None:
                raise CourseServiceError(f'Course "{clean_name}" already exists.')

        context = {
            "course_name": clean_name,
            "course_code": clean_code or "",
            "semester": semester.name,
        }
        category_name = self.template.render_category_name(context).strip()
        _validate_rendered_name(category_name, "Course category")
        reason = f"Discord Bot: course create requested by user {requested_by}"
        created: list[str] = []

        try:
            category = await self._resolve_or_create_category(
                guild, course, category_name, reason, created
            )
            managed = {
                item.template_key: item
                for item in self.database.get_course_channels(course.id)
            }
            for channel_template in self.template.channels:
                await self._resolve_or_create_channel(
                    guild,
                    course,
                    category,
                    channel_template,
                    context,
                    managed.get(channel_template.key),
                    reason,
                    created,
                )
            for definition in bulk_definitions:
                await self._resolve_or_create_bulk_channel(
                    guild, course, category, definition, reason, created
                )
            self.database.mark_course_active(course.id)
        except CourseServiceError as error:
            if created:
                raise CourseProvisionError(str(error), created) from error
            raise
        except discord.Forbidden as error:
            raise CourseProvisionError(
                "Discord denied the operation. Check the bot's Manage Channels "
                "permission and role placement.",
                created,
            ) from error
        except discord.HTTPException as error:
            raise CourseProvisionError(
                "Discord could not complete the operation. Retry the command to "
                "continue the saved partial course.",
                created,
            ) from error
        except sqlite3.Error as error:
            raise CourseProvisionError(
                "The local database could not save the complete operation. Stop "
                "and inspect the local log before retrying.",
                created,
            ) from error

        completed = self.database.get_course(guild.id, clean_name)
        if completed is None:
            raise RuntimeError("The completed course record could not be loaded")
        return CourseCreationResult(completed, tuple(created), resumed)

    def sync_courses(
        self, guild: discord.Guild, *, name: str | None = None
    ) -> list[CourseSyncResult]:
        if name is None:
            courses = self.database.list_courses(guild.id)
        else:
            clean_name = clean_entity_name(name, "Course name", 100)
            course = self.database.get_course(guild.id, clean_name)
            if course is None:
                raise CourseServiceError(f'Course "{clean_name}" is not managed.')
            courses = [course]

        if not courses:
            raise CourseServiceError("No managed courses found.")

        try:
            return [self._sync_course(guild, course) for course in courses]
        except sqlite3.Error as error:
            raise CourseServiceError(
                "The current Discord state could not be saved to the local database."
            ) from error

    def _sync_course(
        self, guild: discord.Guild, course: Course
    ) -> CourseSyncResult:
        context = {
            "course_name": course.name,
            "course_code": course.code or "",
            "semester": course.semester_name,
        }
        expected_category_name = self.template.render_category_name(context).strip()
        category: discord.CategoryChannel | None = None
        category_issue: str | None = None
        category_rebound = False

        if course.category_id is not None:
            saved_category = guild.get_channel(course.category_id)
            if isinstance(saved_category, discord.CategoryChannel):
                category = saved_category

        if category is None:
            candidates = [
                candidate
                for candidate in guild.categories
                if candidate.name.casefold() == expected_category_name.casefold()
            ]
            if len(candidates) == 1:
                category = candidates[0]
                self.database.set_course_category(course.id, category.id)
                category_rebound = True
            elif len(candidates) > 1:
                category_issue = (
                    f'multiple categories are named "{expected_category_name}"'
                )
            else:
                category_issue = "saved category is missing"

        managed_by_key = {
            item.template_key: item
            for item in self.database.get_course_channels(course.id)
        }
        assigned_ids: set[int] = set()
        observed: dict[int, ObservedChannel] = {}
        accepted_changes: list[str] = []
        rebound: list[str] = []
        missing: list[str] = []
        ambiguous: list[str] = []

        if category is not None and category.name != expected_category_name:
            accepted_changes.append(
                f'category renamed to "{category.name}"'
            )

        for template in self.template.channels:
            expected_name = template.render_name(context).strip()
            managed = managed_by_key.get(template.key)
            channel = (
                guild.get_channel(managed.discord_channel_id)
                if managed is not None
                else None
            )

            if channel is None and category is not None:
                candidates = [
                    candidate
                    for candidate in category.channels
                    if candidate.id not in assigned_ids
                    and candidate.id
                    not in self._other_owned_channel_ids(course.id, None)
                    and candidate.name.casefold() == expected_name.casefold()
                    and _matches_type(candidate, template.type)
                ]
                if len(candidates) == 1:
                    channel = candidates[0]
                    if managed is None:
                        self.database.add_course_channel(
                            course.id, template.key, channel.id, template.type
                        )
                    else:
                        self.database.rebind_course_channel(
                            course.id, template.key, channel.id, template.type
                        )
                    rebound.append(f'{template.key} → #{channel.name}')
                elif len(candidates) > 1:
                    ambiguous.append(
                        f'{template.key}: multiple matching channels named '
                        f'"{expected_name}"'
                    )

            if channel is None:
                if not any(item.startswith(f"{template.key}:") for item in ambiguous):
                    missing.append(template.key)
                continue

            assigned_ids.add(channel.id)
            actual_type = _channel_type(channel)
            actual_category_id = getattr(channel, "category_id", None)
            observed[channel.id] = ObservedChannel(
                discord_channel_id=channel.id,
                name=channel.name,
                channel_type=actual_type,
                category_id=actual_category_id,
                template_key=template.key,
            )
            if channel.name != expected_name:
                accepted_changes.append(
                    f'{template.key} renamed to "{channel.name}"'
                )
            if category is not None and actual_category_id != category.id:
                accepted_changes.append(f"{template.key} moved outside the category")
            if not _matches_type(channel, template.type):
                accepted_changes.append(
                    f"{template.key} type is now {actual_type}"
                )

        for definition in self.database.list_bulk_channel_definitions(guild.id):
            label = f"shared:{definition.name}"
            binding = self.database.get_bulk_channel_binding(
                definition.id, course.id
            )
            channel = (
                guild.get_channel(binding.discord_channel_id)
                if binding is not None
                else None
            )
            if channel is None and category is not None:
                candidates = [
                    candidate
                    for candidate in category.channels
                    if candidate.id not in assigned_ids
                    and candidate.id
                    not in self._other_owned_channel_ids(course.id, definition.id)
                    and candidate.name.casefold() == definition.name.casefold()
                    and _matches_type(candidate, definition.channel_type)
                ]
                if len(candidates) == 1:
                    channel = candidates[0]
                    if binding is None:
                        self.database.add_bulk_channel_binding(
                            definition.id, course.id, channel.id
                        )
                    else:
                        self.database.rebind_bulk_channel(
                            definition.id, course.id, channel.id
                        )
                    rebound.append(f"{label} → #{channel.name}")
                elif len(candidates) > 1:
                    ambiguous.append(
                        f'{label}: multiple matching channels named '
                        f'"{definition.name}"'
                    )
            if channel is None:
                if not any(item.startswith(f"{label}:") for item in ambiguous):
                    missing.append(label)
                continue

            assigned_ids.add(channel.id)
            actual_type = _channel_type(channel)
            actual_category_id = getattr(channel, "category_id", None)
            observed[channel.id] = ObservedChannel(
                discord_channel_id=channel.id,
                name=channel.name,
                channel_type=actual_type,
                category_id=actual_category_id,
                template_key=label,
            )
            if channel.name != definition.name:
                accepted_changes.append(f'{label} renamed to "{channel.name}"')
            if category is not None and actual_category_id != category.id:
                accepted_changes.append(f"{label} moved outside the category")
            if not _matches_type(channel, definition.channel_type):
                accepted_changes.append(f"{label} type is now {actual_type}")

        additional: list[str] = []
        if category is not None:
            for channel in category.channels:
                if channel.id in observed:
                    continue
                actual_type = _channel_type(channel)
                observed[channel.id] = ObservedChannel(
                    discord_channel_id=channel.id,
                    name=channel.name,
                    channel_type=actual_type,
                    category_id=getattr(channel, "category_id", None),
                    template_key=None,
                )
                additional.append(f'#{channel.name} ({actual_type})')

        self.database.save_course_sync_snapshot(
            course.id,
            category_present=category is not None,
            category_name=category.name if category is not None else None,
            channels=list(observed.values()),
        )
        return CourseSyncResult(
            course=course,
            category_name=category.name if category is not None else None,
            category_issue=category_issue,
            category_rebound=category_rebound,
            present_count=len(observed),
            accepted_changes=tuple(accepted_changes),
            rebound=tuple(rebound),
            missing=tuple(missing),
            ambiguous=tuple(ambiguous),
            additional=tuple(additional),
        )

    async def add_bulk_channel(
        self,
        guild: discord.Guild,
        *,
        name: str,
        channel_type: str,
        topic: str | None,
        confirm: bool,
        requested_by: int,
    ) -> BulkChannelAddResult:
        clean_name = clean_entity_name(name, "Channel name", 100)
        clean_type = _validate_channel_type(channel_type)
        clean_topic = clean_optional_topic(topic, clean_type)
        courses = self.database.list_courses(guild.id)
        if not courses:
            raise CourseServiceError("No managed courses found.")
        for course in courses:
            context = {
                "course_name": course.name,
                "course_code": course.code or "",
                "semester": course.semester_name,
            }
            if any(
                template.render_name(context).strip().casefold()
                == clean_name.casefold()
                for template in self.template.channels
            ):
                raise CourseServiceError(
                    f'Channel name "{clean_name}" is already reserved by the '
                    "course template."
                )

        definition = self.database.get_bulk_channel_definition(guild.id, clean_name)
        definition_existed = definition is not None
        if definition is not None and (
            definition.channel_type != clean_type or definition.topic != clean_topic
        ):
            raise CourseServiceError(
                f'A bulk channel named "{definition.name}" already exists with '
                "different settings."
            )

        plan = self._plan_bulk_channel_add(
            guild, courses, definition, clean_name, clean_type
        )
        if not confirm:
            return BulkChannelAddResult(
                clean_name,
                clean_type,
                False,
                len(courses),
                tuple(plan["create"]),
                tuple(plan["reconnect"]),
                tuple(plan["already"]),
                tuple(plan["conflicts"]),
                (),
            )

        self._require_manage_channels(guild)
        if clean_type == "forum" and "COMMUNITY" not in guild.features:
            raise CourseServiceError(
                "Forum channels require Community to be enabled on this server."
            )
        if definition is None:
            definition = self.database.create_bulk_channel_definition(
                guild.id, clean_name, clean_type, clean_topic
            )
            if definition is None:
                raise CourseServiceError(
                    "The bulk channel definition was created concurrently; retry."
                )

        created: list[str] = []
        conflicts = list(plan["conflicts"])
        reason = f"Discord Bot: bulk channel add requested by user {requested_by}"
        for course in courses:
            category = guild.get_channel(course.category_id) if course.category_id else None
            if not isinstance(category, discord.CategoryChannel):
                continue
            binding = self.database.get_bulk_channel_binding(definition.id, course.id)
            live = guild.get_channel(binding.discord_channel_id) if binding else None
            if live is not None:
                continue

            candidates = [
                channel
                for channel in category.channels
                if channel.name.casefold() == clean_name.casefold()
                and _matches_type(channel, clean_type)
                and channel.id
                not in self._other_owned_channel_ids(course.id, definition.id)
            ]
            if definition_existed and len(candidates) == 1:
                if binding is None:
                    self.database.add_bulk_channel_binding(
                        definition.id, course.id, candidates[0].id
                    )
                else:
                    self.database.rebind_bulk_channel(
                        definition.id, course.id, candidates[0].id
                    )
                continue
            if candidates or any(
                channel.name.casefold() == clean_name.casefold()
                for channel in category.channels
            ):
                continue
            try:
                channel = await _create_channel(
                    guild,
                    category,
                    name=clean_name,
                    channel_type=clean_type,
                    topic=clean_topic,
                    reason=reason,
                )
                self.database.add_bulk_channel_binding(
                    definition.id, course.id, channel.id
                )
                created.append(course.name)
            except (discord.Forbidden, discord.HTTPException) as error:
                conflicts.append(f"{course.name}: Discord error ({error.code})")

        return BulkChannelAddResult(
            clean_name,
            clean_type,
            True,
            len(courses),
            tuple(plan["create"]),
            tuple(plan["reconnect"]),
            tuple(plan["already"]),
            tuple(conflicts),
            tuple(created),
        )

    def _plan_bulk_channel_add(
        self,
        guild: discord.Guild,
        courses: list[Course],
        definition: BulkChannelDefinition | None,
        name: str,
        channel_type: str,
    ) -> dict[str, list[str]]:
        plan = {"create": [], "reconnect": [], "already": [], "conflicts": []}
        for course in courses:
            category = guild.get_channel(course.category_id) if course.category_id else None
            if not isinstance(category, discord.CategoryChannel):
                plan["conflicts"].append(f"{course.name}: category is missing")
                continue
            binding = (
                self.database.get_bulk_channel_binding(definition.id, course.id)
                if definition is not None
                else None
            )
            live = guild.get_channel(binding.discord_channel_id) if binding else None
            if live is not None:
                plan["already"].append(course.name)
                continue
            same_name = [
                channel
                for channel in category.channels
                if channel.name.casefold() == name.casefold()
            ]
            matching = [
                channel
                for channel in same_name
                if _matches_type(channel, channel_type)
                and channel.id
                not in self._other_owned_channel_ids(
                    course.id, definition.id if definition is not None else None
                )
            ]
            if definition is not None and len(matching) == 1:
                plan["reconnect"].append(course.name)
            elif same_name:
                plan["conflicts"].append(
                    f'{course.name}: untracked or ambiguous channel named "{name}"'
                )
            else:
                plan["create"].append(course.name)
        return plan

    def _other_owned_channel_ids(
        self, course_id: int, current_definition_id: int | None
    ) -> set[int]:
        owned = {
            channel.discord_channel_id
            for channel in self.database.get_course_channels(course_id)
        }
        owned.update(
            binding.discord_channel_id
            for binding in self.database.list_bulk_channel_bindings_for_course(
                course_id
            )
            if binding.definition_id != current_definition_id
        )
        return owned

    async def delete_bulk_channel(
        self,
        guild: discord.Guild,
        *,
        name: str,
        confirm: bool,
        requested_by: int,
    ) -> BulkChannelDeleteResult:
        clean_name = clean_entity_name(name, "Channel name", 100)
        definition = self.database.get_bulk_channel_definition(guild.id, clean_name)
        if definition is None:
            raise CourseServiceError(
                f'Bulk channel "{clean_name}" is not managed. Nothing was deleted.'
            )
        bindings = self.database.list_bulk_channel_bindings(definition.id)
        courses = {course.id: course for course in self.database.list_courses(guild.id)}
        live: list[str] = []
        missing: list[str] = []
        for binding in bindings:
            course_name = courses.get(binding.course_id)
            label = course_name.name if course_name is not None else str(binding.course_id)
            if guild.get_channel(binding.discord_channel_id) is None:
                missing.append(label)
            else:
                live.append(label)
        if not confirm:
            return BulkChannelDeleteResult(
                definition, False, tuple(live), tuple(missing), (), (), False
            )

        self._require_manage_channels(guild)
        deleted: list[str] = []
        failures: list[str] = []
        reason = f"Discord Bot: bulk channel delete requested by user {requested_by}"
        for binding in bindings:
            course = courses.get(binding.course_id)
            label = course.name if course is not None else str(binding.course_id)
            channel = guild.get_channel(binding.discord_channel_id)
            if channel is not None:
                try:
                    await channel.delete(reason=reason)
                    deleted.append(label)
                except (discord.Forbidden, discord.HTTPException) as error:
                    failures.append(f"{label}: Discord error ({error.code})")
                    continue
            self.database.remove_bulk_channel_binding(
                definition.id, binding.course_id
            )
        definition_removed = self.database.delete_bulk_channel_definition(definition.id)
        return BulkChannelDeleteResult(
            definition,
            True,
            tuple(live),
            tuple(missing),
            tuple(deleted),
            tuple(failures),
            definition_removed,
        )

    async def delete_course(
        self,
        guild: discord.Guild,
        *,
        name: str,
        confirm: bool,
        requested_by: int,
    ) -> CourseDeleteResult:
        clean_name = clean_entity_name(name, "Course name", 100)
        course = self.database.get_course(guild.id, clean_name)
        if course is None:
            raise CourseServiceError(
                f'Course "{clean_name}" is not managed. Nothing was deleted.'
            )
        owned_ids = {
            channel.discord_channel_id
            for channel in self.database.get_course_channels(course.id)
        }
        owned_ids.update(
            binding.discord_channel_id
            for binding in self.database.list_bulk_channel_bindings_for_course(course.id)
        )
        managed_live: list[str] = []
        managed_missing: list[str] = []
        for channel_id in sorted(owned_ids):
            channel = guild.get_channel(channel_id)
            if channel is None:
                managed_missing.append(str(channel_id))
            else:
                managed_live.append(f"#{channel.name} (`{channel.id}`)")
        category = guild.get_channel(course.category_id) if course.category_id else None
        if not isinstance(category, discord.CategoryChannel):
            category = None
        manual_kept = (
            [f"#{channel.name} (`{channel.id}`)" for channel in category.channels
             if channel.id not in owned_ids]
            if category is not None
            else []
        )
        category_will_delete = category is not None and not manual_kept
        if not confirm:
            return CourseDeleteResult(
                course,
                False,
                tuple(managed_live),
                tuple(managed_missing),
                tuple(manual_kept),
                category_will_delete,
                (),
                (),
                False,
            )

        self._require_manage_channels(guild)
        deleted: list[str] = []
        failures: list[str] = []
        reason = f"Discord Bot: course delete requested by user {requested_by}"
        for channel_id in sorted(owned_ids):
            channel = guild.get_channel(channel_id)
            if channel is None:
                continue
            try:
                await channel.delete(reason=reason)
                deleted.append(f"#{channel.name}")
            except (discord.Forbidden, discord.HTTPException) as error:
                failures.append(f"#{channel.name}: Discord error ({error.code})")
        if not failures and category_will_delete and category is not None:
            try:
                await category.delete(reason=reason)
                deleted.append(f"category: {category.name}")
            except (discord.Forbidden, discord.HTTPException) as error:
                failures.append(f"category {category.name}: Discord error ({error.code})")
        record_removed = False
        if not failures:
            record_removed = self.database.delete_course(course.id)
        return CourseDeleteResult(
            course,
            True,
            tuple(managed_live),
            tuple(managed_missing),
            tuple(manual_kept),
            category_will_delete,
            tuple(deleted),
            tuple(failures),
            record_removed,
        )

    def _require_manage_channels(self, guild: discord.Guild) -> None:
        bot_member = guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_channels:
            raise CourseServiceError(
                "The bot needs the Manage Channels permission for this operation."
            )

    async def _resolve_or_create_category(
        self,
        guild: discord.Guild,
        course: Course,
        category_name: str,
        reason: str,
        created: list[str],
    ) -> discord.CategoryChannel:
        if course.category_id is not None:
            channel = guild.get_channel(course.category_id)
            if not isinstance(channel, discord.CategoryChannel):
                raise CourseServiceError(
                    "The saved course category is missing or has the wrong type."
                )
            return channel

        if any(
            category.name.casefold() == category_name.casefold()
            for category in guild.categories
        ):
            raise CourseServiceError(
                f'A category named "{category_name}" already exists but is not managed.'
            )

        category = await guild.create_category(category_name, reason=reason)
        created.append(f"category: {category.name}")
        self.database.set_course_category(course.id, category.id)
        return category

    async def _resolve_or_create_channel(
        self,
        guild: discord.Guild,
        course: Course,
        category: discord.CategoryChannel,
        template: ChannelTemplate,
        context: dict[str, str],
        managed: ManagedChannel | None,
        reason: str,
        created: list[str],
    ) -> None:
        expected_name = template.render_name(context).strip()
        _validate_rendered_name(expected_name, f'Channel "{template.key}"')

        if managed is not None:
            channel = guild.get_channel(managed.discord_channel_id)
            if channel is None or not _matches_type(channel, template.type):
                raise CourseServiceError(
                    f'The saved channel "{template.key}" is missing or has the wrong type.'
                )
            # Discord is authoritative: a manual move must not be reverted when
            # an incomplete course creation later resumes.
            return

        if any(
            channel.name.casefold() == expected_name.casefold()
            for channel in category.channels
        ):
            raise CourseServiceError(
                f'Channel "{expected_name}" already exists but is not managed.'
            )

        topic = template.render_topic(context)
        if template.type == "text":
            channel = await guild.create_text_channel(
                expected_name, category=category, topic=topic, reason=reason
            )
            label = f"#{channel.name}"
        elif template.type == "forum":
            tags = [discord.ForumTag(name=tag) for tag in template.tags]
            channel = await guild.create_forum(
                expected_name,
                category=category,
                topic=topic,
                available_tags=tags,
                reason=reason,
            )
            label = f"forum: {channel.name}"
        else:
            channel = await guild.create_voice_channel(
                expected_name, category=category, reason=reason
            )
            label = f"voice: {channel.name}"

        created.append(label)
        self.database.add_course_channel(
            course.id, template.key, channel.id, template.type
        )

    async def _resolve_or_create_bulk_channel(
        self,
        guild: discord.Guild,
        course: Course,
        category: discord.CategoryChannel,
        definition: BulkChannelDefinition,
        reason: str,
        created: list[str],
    ) -> None:
        binding = self.database.get_bulk_channel_binding(definition.id, course.id)
        if binding is not None:
            channel = guild.get_channel(binding.discord_channel_id)
            if channel is not None:
                return

        same_name = [
            channel
            for channel in category.channels
            if channel.name.casefold() == definition.name.casefold()
        ]
        matching = [
            channel
            for channel in same_name
            if _matches_type(channel, definition.channel_type)
            and channel.id
            not in self._other_owned_channel_ids(course.id, definition.id)
        ]
        if binding is not None and len(matching) == 1:
            self.database.rebind_bulk_channel(
                definition.id, course.id, matching[0].id
            )
            return
        if same_name:
            raise CourseServiceError(
                f'Bulk channel "{definition.name}" conflicts with an untracked '
                "or ambiguous channel."
            )

        channel = await _create_channel(
            guild,
            category,
            name=definition.name,
            channel_type=definition.channel_type,
            topic=definition.topic,
            reason=reason,
        )
        created.append(f"bulk {definition.channel_type}: #{channel.name}")
        if binding is None:
            self.database.add_bulk_channel_binding(
                definition.id, course.id, channel.id
            )
        else:
            self.database.rebind_bulk_channel(
                definition.id, course.id, channel.id
            )


def clean_entity_name(value: str, label: str, maximum: int) -> str:
    cleaned = " ".join(value.split())
    if not cleaned or len(cleaned) > maximum:
        raise CourseServiceError(f"{label} must contain 1-{maximum} characters.")
    return cleaned


def clean_optional_code(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    if len(cleaned) > 32:
        raise CourseServiceError("Course code must contain at most 32 characters.")
    return cleaned


def clean_optional_topic(value: str | None, channel_type: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if channel_type == "voice":
        raise CourseServiceError("Voice channels cannot have a topic.")
    if len(cleaned) > 1024:
        raise CourseServiceError("Channel topic must contain at most 1024 characters.")
    return cleaned


def _validate_channel_type(value: str) -> str:
    if value not in {"text", "forum", "voice"}:
        raise CourseServiceError("Channel type must be text, forum, or voice.")
    return value


def _validate_rendered_name(value: str, label: str) -> None:
    if not value or len(value) > 100:
        raise CourseServiceError(f"{label} must render to 1-100 characters.")


def _matches_type(channel: discord.abc.GuildChannel, expected: str) -> bool:
    expected_class: type[discord.abc.GuildChannel]
    if expected == "text":
        expected_class = discord.TextChannel
    elif expected == "forum":
        expected_class = discord.ForumChannel
    else:
        expected_class = discord.VoiceChannel
    return isinstance(channel, expected_class)


def _channel_type(channel: discord.abc.GuildChannel) -> str:
    if isinstance(channel, discord.ForumChannel):
        return "forum"
    if isinstance(channel, discord.VoiceChannel):
        return "voice"
    if isinstance(channel, discord.TextChannel):
        return "text"
    return str(channel.type)


async def _create_channel(
    guild: discord.Guild,
    category: discord.CategoryChannel,
    *,
    name: str,
    channel_type: str,
    topic: str | None,
    reason: str,
) -> discord.abc.GuildChannel:
    if channel_type == "text":
        return await guild.create_text_channel(
            name, category=category, topic=topic, reason=reason
        )
    if channel_type == "forum":
        return await guild.create_forum(
            name, category=category, topic=topic, reason=reason
        )
    return await guild.create_voice_channel(name, category=category, reason=reason)
