from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def start_menu():
    """Inline клавиатура для стартового меню (устаревшая, используется для обратной совместимости)"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔑 Получить ключ", callback_data="get_key")
    kb.button(text="❓О нас", callback_data="help")
    kb.adjust(2)
    return kb.as_markup()


def main_menu():
    """Основная клавиатура с обычными кнопками для пользователей"""
    kb = ReplyKeyboardBuilder()
    kb.button(text="👤 Профиль")
    kb.button(text="🛒 Покупка")
    kb.button(text="📖 Инструкции")
    kb.button(text="💬 Поддержка")
    kb.adjust(2, 2)
    # Используем is_persistent=True, чтобы кнопки оставались видимыми даже после inline-кнопок
    # и one_time_keyboard=False, чтобы кнопки не скрывались после использования
    return kb.as_markup(resize_keyboard=True, is_persistent=True, one_time_keyboard=False)


def instructions_platform_keyboard():
    """Клавиатура выбора платформы для инструкций"""
    kb = InlineKeyboardBuilder()
    kb.button(text="💻 ПК", callback_data="instructions_pc")
    kb.button(text="📱 Телефоны", callback_data="instructions_mobile")
    kb.adjust(2)
    return kb.as_markup()


def instructions_more_keyboard(platform: str):
    """Клавиатура с кнопкой 'Узнать больше' для инструкций"""
    kb = InlineKeyboardBuilder()
    kb.button(text="📚 Узнать больше", callback_data=f"instructions_more_{platform}")
    kb.button(text="🔙 Назад к выбору", callback_data="instructions_back")
    kb.adjust(1)
    return kb.as_markup()
