from loguru import logger

logger.add("bot.log", format="{time} {level} {message}", level="INFO")
