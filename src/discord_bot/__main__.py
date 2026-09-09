from __future__ import annotations

import logging

from dotenv import load_dotenv

from .app import AdminBot
from .config import ConfigError, load_settings
from .logging_config import configure_logging
from .template import load_course_template


def main() -> int:
    load_dotenv()

    try:
        settings = load_settings()
        course_template = load_course_template(settings.course_template_path)
    except ConfigError as error:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
        logging.getLogger(__name__).error("Configuration error: %s", error)
        return 2

    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    logger.info("Starting Discord Bot")

    bot = AdminBot(settings, course_template)
    bot.run(settings.discord_token, log_handler=None)
    logger.info("Discord Bot stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
