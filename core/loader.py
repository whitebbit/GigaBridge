from aiogram import Bot, Dispatcher
from core.config import config
from core.storage import fsm_storage

bot = Bot(token=config.BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(storage=fsm_storage)
