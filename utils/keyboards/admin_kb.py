from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models import Server, User


def admin_menu():
    """Главное меню админ-панели"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🌍 Локации", callback_data="admin_locations")
    kb.button(text="🖥️ Серверы", callback_data="admin_servers")
    kb.button(text="👥 Пользователи", callback_data="admin_users")
    kb.button(text="🎟️ Промокоды", callback_data="admin_promocodes")
    kb.button(text="📖 Инструкции", callback_data="admin_tutorials")
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    kb.button(text="📢 Рассылка", callback_data="admin_broadcast")
    kb.button(text="💬 Поддержка", callback_data="admin_support")
    kb.button(text="🔙 Назад", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def servers_menu():
    """Меню управления серверами"""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить", callback_data="admin_server_add")
    kb.button(text="📋 Список", callback_data="admin_server_list")
    kb.button(text="🔙 Назад", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def server_list_keyboard(servers: list[Server]):
    """Клавиатура со списком серверов"""
    kb = InlineKeyboardBuilder()
    for server in servers:
        status = "✅" if server.is_active else "❌"
        kb.button(
            text=f"{status} {server.name}",
            callback_data=f"admin_server_edit_{server.id}"
        )
    kb.button(text="🔙 Назад", callback_data="admin_servers")
    kb.adjust(1)
    return kb.as_markup()


def server_edit_keyboard(server_id: int):
    """Клавиатура для редактирования сервера"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Название", callback_data=f"admin_server_edit_name_{server_id}")
    kb.button(text="🌍 Локация", callback_data=f"admin_server_edit_location_{server_id}")
    kb.button(text="📝 Описание", callback_data=f"admin_server_edit_description_{server_id}")
    kb.button(text="🔗 API URL", callback_data=f"admin_server_edit_api_url_{server_id}")
    kb.button(text="👤 Username", callback_data=f"admin_server_edit_api_username_{server_id}")
    kb.button(text="🔑 Password", callback_data=f"admin_server_edit_api_password_{server_id}")
    kb.button(text="🔒 SSL Сертификат", callback_data=f"admin_server_edit_ssl_cert_{server_id}")
    kb.button(text="📋 Sub URL", callback_data=f"admin_server_edit_sub_url_{server_id}")
    kb.button(text="👥 Макс. юзеры", callback_data=f"admin_server_edit_max_users_{server_id}")
    kb.button(text="💰 Период оплаты", callback_data=f"admin_server_edit_payment_days_{server_id}")
    kb.button(text="🔍 Проверка соединения", callback_data=f"admin_server_test_connection_{server_id}")
    kb.button(text="📢 Уведомить пользователей", callback_data=f"admin_server_notify_users_{server_id}")
    kb.button(text="🔄 Статус", callback_data=f"admin_server_toggle_{server_id}")
    kb.button(text="🗑️ Удалить", callback_data=f"admin_server_delete_{server_id}")
    kb.button(text="🔙 Назад", callback_data="admin_server_list")
    kb.adjust(2, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1)
    return kb.as_markup()


def confirm_delete_keyboard(server_id: int):
    """Клавиатура подтверждения удаления"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data=f"admin_server_delete_confirm_{server_id}")
    kb.button(text="❌ Отмена", callback_data=f"admin_server_edit_{server_id}")
    kb.adjust(2)
    return kb.as_markup()


def confirm_delete_all_subscriptions_keyboard(user_id: int):
    """Клавиатура подтверждения удаления всех подписок пользователя"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить все", callback_data=f"admin_user_delete_all_subscriptions_confirm_{user_id}")
    kb.button(text="❌ Отмена", callback_data=f"admin_user_view_{user_id}")
    kb.adjust(2)
    return kb.as_markup()


def cancel_keyboard():
    """Клавиатура отмены"""
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="cancel")
    return kb.as_markup()


def users_menu():
    """Меню управления пользователями"""
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список пользователей", callback_data="admin_user_list")
    kb.button(text="🔍 Поиск пользователя", callback_data="admin_user_search")
    kb.button(text="🔙 Назад", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def user_list_keyboard(users: list[User], page: int = 0, total_pages: int = 1):
    """Клавиатура со списком пользователей с пагинацией"""
    kb = InlineKeyboardBuilder()
    
    # Кнопки пользователей
    for user in users:
        admin_badge = "👑 " if user.is_admin else ""
        status_emoji = {
            "active": "✅",
            "paused": "⏸️",
            "expired": "❌"
        }.get(user.status, "❓")
        
        username = user.username or f"ID: {user.tg_id}"
        display_name = f"{status_emoji} {admin_badge}{username[:25]}"
        kb.button(
            text=display_name,
            callback_data=f"admin_user_view_{user.id}"
        )
    
    # Кнопки пагинации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(("◀️ Назад", f"admin_users_page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(("Вперед ▶️", f"admin_users_page_{page + 1}"))
    
    for text, callback_data in nav_buttons:
        kb.button(text=text, callback_data=callback_data)
    
    # Кнопка возврата
    kb.button(text="🔙 Назад", callback_data="admin_users")
    
    # Настройка расположения: пользователи по 1, навигация в ряд, назад отдельно
    if nav_buttons:
        kb.adjust(1, len(nav_buttons), 1)
    else:
        kb.adjust(1)
    
    return kb.as_markup()


def user_detail_keyboard(user_id: int, is_admin: bool, subscriptions=None):
    """Клавиатура для деталей пользователя"""
    kb = InlineKeyboardBuilder()
    
    # Кнопка переключения статуса администратора
    if is_admin:
        kb.button(text="👑 Убрать права админа", callback_data=f"admin_user_toggle_admin_{user_id}")
    else:
        kb.button(text="👑 Назначить админом", callback_data=f"admin_user_toggle_admin_{user_id}")
    
    # Кнопка отправки сообщения
    kb.button(text="📨 Отправить сообщение", callback_data=f"admin_user_send_message_{user_id}")
    
    # Кнопка создания подписки
    kb.button(text="➕ Выдать подписку", callback_data=f"admin_user_create_subscription_{user_id}")
    
    # Кнопки управления подписками (3 в ряду)
    if subscriptions:
        kb.button(text="─" * 20, callback_data="noop")
        # Группируем подписки по 3 в ряд
        for i in range(0, len(subscriptions), 3):
            row_subs = subscriptions[i:i+3]
            for sub in row_subs:
                # Получаем информацию о локации для отображения
                from utils.db import get_subscription_identifier
                # Используем упрощенный идентификатор
                sub_id_display = f"#{sub.id}"
                status_emoji = "✅" if sub.status == "active" else "⏸️" if sub.status == "paused" else "❌"
                kb.button(
                    text=f"{status_emoji} {sub_id_display}",
                    callback_data=f"admin_subscription_view_{sub.id}"
                )
        
        # Кнопка удаления всех подписок пользователя
        kb.button(text="🗑️ Удалить все подписки", callback_data=f"admin_user_delete_all_subscriptions_{user_id}")
    
    kb.button(text="🔙 Назад", callback_data="admin_user_list")
    
    # Настройка расположения: 
    # Первая строка: 👑 Назначить админом | 📨 Отправить сообщение (2 кнопки)
    # Вторая строка: ➕ Выдать подписку (1 кнопка)
    # Затем разделитель (1), подписки (3 в ряд), удалить все (1), назад (1)
    if subscriptions:
        # Подсчитываем количество строк для подписок
        subscription_rows = (len(subscriptions) + 2) // 3  # +2 для округления вверх
        adjust_list = [2, 1, 1]  # Админ+сообщение (2), создать (1), разделитель (1)
        adjust_list.extend([3] * subscription_rows)  # Подписки по 3 в ряд
        adjust_list.extend([1, 1])  # Удалить все, назад
        kb.adjust(*adjust_list)
    else:
        kb.adjust(2, 1, 1)  # Админ+сообщение (2), создать (1), назад (1)
    
    return kb.as_markup()


def stats_keyboard():
    """Клавиатура для статистики"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить", callback_data="admin_stats")
    kb.button(text="🔙 Назад", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()

