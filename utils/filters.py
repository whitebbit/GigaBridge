from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from typing import Union
from utils.db import is_admin


class AdminFilter(BaseFilter):
    """Фильтр для проверки прав администратора"""
    
    async def __call__(self, obj: Union[Message, CallbackQuery]) -> bool:
        user_id = str(obj.from_user.id)
        return await is_admin(user_id)


class SimpleEditServerFilter(BaseFilter):
    """Фильтр для обработки простого callback редактирования сервера (admin_server_edit_{id})"""
    
    async def __call__(self, obj: CallbackQuery) -> bool:
        if not isinstance(obj, CallbackQuery):
            return False
        data = obj.data
        if not data.startswith("admin_server_edit_"):
            return False
        # Проверяем, что это не специфичный callback
        if any(data.startswith(prefix) for prefix in [
            "admin_server_edit_name_",
            "admin_server_edit_price_",
            "admin_server_edit_location_",
            "admin_server_edit_description_",
            "admin_server_edit_api_url_",
            "admin_server_edit_api_key_",
            "admin_server_edit_max_users_"
        ]):
            return False
        # Проверяем, что после "admin_server_edit_" идет только число
        suffix = data.replace("admin_server_edit_", "")
        return suffix.isdigit()
