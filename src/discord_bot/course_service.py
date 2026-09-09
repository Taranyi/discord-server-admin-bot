from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import discord

from .database import Course, Database, ManagedChannel, ObservedChannel, normalize_name
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

        bot_member = guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_channels:
            raise CourseServiceError(
                "The bot needs the Manage Channels permission to create a course."
            )
        if self.template.requires_community and "COMMUNITY" not in guild.features:
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
