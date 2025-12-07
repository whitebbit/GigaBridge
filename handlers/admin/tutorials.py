"""
Обработчики для управления инструкциями (платформами и туториалами) в админ-панели
"""
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from utils.filters import AdminFilter
from utils.keyboards.admin_kb import admin_menu, cancel_keyboard
import html
from utils.db import (
    get_all_platforms,
    get_active_platforms,
    get_platform_by_id,
    get_platform_by_name,
    create_platform,
    update_platform,
    delete_platform,
    get_tutorials_by_platform,
    get_tutorial_by_id,
    create_tutorial,
    update_tutorial,
    delete_tutorial,
    get_tutorial_files,
    add_tutorial_file,
    delete_tutorial_file,
    get_basic_tutorial_for_platform,
    get_additional_tutorials_for_platform
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


async def safe_edit_text(message: types.Message, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения"""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


def tutorials_menu():
    """Меню управления инструкциями"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 Платформы", callback_data="admin_tutorials_platforms")
    kb.button(text="📖 Туториалы", callback_data="admin_tutorials_list")
    kb.button(text="🔙 Назад", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def platforms_menu():
    """Меню управления платформами"""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить платформу", callback_data="admin_platform_add")
    kb.button(text="📋 Список платформ", callback_data="admin_platform_list")
    kb.button(text="🔙 Назад", callback_data="admin_tutorials")
    kb.adjust(1)
    return kb.as_markup()


def platform_list_keyboard(platforms: list):
    """Клавиатура со списком платформ"""
    kb = InlineKeyboardBuilder()
    for platform in platforms:
        status = "✅" if platform.is_active else "❌"
        kb.button(
            text=f"{status} {platform.display_name}",
            callback_data=f"admin_platform_edit_{platform.id}"
        )
    kb.button(text="🔙 Назад", callback_data="admin_tutorials_platforms")
    kb.adjust(1)
    return kb.as_markup()


def platform_edit_keyboard(platform_id: int):
    """Клавиатура для редактирования платформы"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить название", callback_data=f"admin_platform_edit_name_{platform_id}")
    kb.button(text="📝 Изменить описание", callback_data=f"admin_platform_edit_description_{platform_id}")
    kb.button(text="🔄 Переключить статус", callback_data=f"admin_platform_toggle_{platform_id}")
    kb.button(text="📖 Управлять туториалами", callback_data=f"admin_platform_tutorials_{platform_id}")
    kb.button(text="🗑️ Удалить платформу", callback_data=f"admin_platform_delete_{platform_id}")
    kb.button(text="🔙 Назад", callback_data="admin_platform_list")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def tutorials_list_keyboard(platform_id: int, tutorials: list):
    """Клавиатура со списком туториалов для платформы"""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить туториал", callback_data=f"admin_tutorial_add_{platform_id}")
    
    for tutorial in tutorials:
        tutorial_type = "📘 Базовый" if tutorial.is_basic else "📗 Дополнительный"
        status = "✅" if tutorial.is_active else "❌"
        kb.button(
            text=f"{status} {tutorial_type}: {tutorial.title[:30]}",
            callback_data=f"admin_tutorial_edit_{tutorial.id}"
        )
    
    kb.button(text="🔙 Назад", callback_data=f"admin_platform_edit_{platform_id}")
    kb.adjust(1)
    return kb.as_markup()


def tutorial_edit_keyboard(tutorial_id: int, platform_id: int):
    """Клавиатура для редактирования туториала"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить заголовок", callback_data=f"admin_tutorial_edit_title_{tutorial_id}")
    kb.button(text="📝 Изменить текст", callback_data=f"admin_tutorial_edit_text_{tutorial_id}")
    kb.button(text="🎥 Загрузить видео", callback_data=f"admin_tutorial_upload_video_{tutorial_id}")
    kb.button(text="📎 Управлять файлами", callback_data=f"admin_tutorial_files_{tutorial_id}")
    kb.button(text="🔄 Переключить тип", callback_data=f"admin_tutorial_toggle_type_{tutorial_id}")
    kb.button(text="🔄 Переключить статус", callback_data=f"admin_tutorial_toggle_status_{tutorial_id}")
    kb.button(text="🗑️ Удалить туториал", callback_data=f"admin_tutorial_delete_{tutorial_id}")
    kb.button(text="🔙 Назад", callback_data=f"admin_platform_tutorials_{platform_id}")
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()


def tutorial_files_keyboard(tutorial_id: int, files: list, platform_id: int):
    """Клавиатура для управления файлами туториала"""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить файл", callback_data=f"admin_tutorial_file_add_{tutorial_id}")
    
    for file in files:
        file_name = file.file_name or f"Файл #{file.id}"
        kb.button(
            text=f"📎 {file_name[:30]}",
            callback_data=f"admin_tutorial_file_delete_{file.id}"
        )
    
    kb.button(text="🔙 Назад", callback_data=f"admin_tutorial_edit_{tutorial_id}")
    kb.adjust(1)
    return kb.as_markup()


# ========== States ==========

class AddPlatformStates(StatesGroup):
    waiting_name = State()
    waiting_display_name = State()
    waiting_description = State()


class EditPlatformStates(StatesGroup):
    waiting_name = State()
    waiting_display_name = State()
    waiting_description = State()


class AddTutorialStates(StatesGroup):
    waiting_title = State()
    waiting_text = State()
    waiting_video = State()


class EditTutorialStates(StatesGroup):
    waiting_title = State()
    waiting_text = State()
    waiting_video = State()


class AddTutorialFileStates(StatesGroup):
    waiting_file = State()


# ========== Главное меню инструкций ==========

@router.callback_query(F.data == "admin_tutorials", AdminFilter())
async def tutorials_menu_callback(callback: types.CallbackQuery):
    """Меню управления инструкциями"""
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "📖 <b>Управление инструкциями</b>\n\n"
        "Выберите действие:",
        reply_markup=tutorials_menu()
    )


@router.callback_query(F.data == "admin_tutorials_list", AdminFilter())
async def tutorials_list_callback(callback: types.CallbackQuery):
    """Список всех туториалов по платформам"""
    await callback.answer()
    platforms = await get_all_platforms()
    
    if not platforms:
        await safe_edit_text(
            callback.message,
            "📖 <b>Список туториалов</b>\n\n"
            "Платформы не найдены. Добавьте первую платформу!",
            reply_markup=tutorials_menu()
        )
        return
    
    text = "📖 <b>Список туториалов</b>\n\n"
    
    for platform in platforms:
        tutorials = await get_tutorials_by_platform(platform.id)
        basic_tutorials = [t for t in tutorials if t.is_basic]
        additional_tutorials = [t for t in tutorials if not t.is_basic]
        
        text += f"🌐 <b>{html.escape(platform.display_name)}</b>\n"
        text += f"   📘 Базовых: {len(basic_tutorials)}\n"
        text += f"   📗 Дополнительных: {len(additional_tutorials)}\n\n"
        
        if tutorials:
            for tutorial in tutorials:
                tutorial_type = "📘" if tutorial.is_basic else "📗"
                status = "✅" if tutorial.is_active else "❌"
                text += f"   {status} {tutorial_type} {html.escape(tutorial.title[:40])}\n"
            text += "\n"
    
    # Создаем клавиатуру с кнопками платформ
    kb = InlineKeyboardBuilder()
    for platform in platforms:
        kb.button(
            text=f"🌐 {platform.display_name}",
            callback_data=f"admin_platform_tutorials_{platform.id}"
        )
    kb.button(text="🔙 Назад", callback_data="admin_tutorials")
    kb.adjust(1)
    
    await safe_edit_text(callback.message, text, reply_markup=kb.as_markup())


# ========== Управление платформами ==========

@router.callback_query(F.data == "admin_tutorials_platforms", AdminFilter())
async def platforms_menu_callback(callback: types.CallbackQuery):
    """Меню управления платформами"""
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🌐 <b>Управление платформами</b>\n\n"
        "Выберите действие:",
        reply_markup=platforms_menu()
    )


@router.callback_query(F.data == "admin_platform_list", AdminFilter())
async def platform_list_callback(callback: types.CallbackQuery):
    """Список платформ"""
    await callback.answer()
    platforms = await get_all_platforms()
    
    if not platforms:
        await safe_edit_text(
            callback.message,
            "📋 <b>Список платформ</b>\n\n"
            "Платформы не найдены. Добавьте первую платформу!",
            reply_markup=platforms_menu()
        )
        return
    
    text = "📋 <b>Список платформ</b>\n\n"
    for platform in platforms:
        status = "✅ Активна" if platform.is_active else "❌ Неактивна"
        tutorials = await get_tutorials_by_platform(platform.id)
        basic_tutorials = [t for t in tutorials if t.is_basic]
        additional_tutorials = [t for t in tutorials if not t.is_basic]
        text += f"{status} <b>{html.escape(platform.display_name)}</b>\n"
        text += f"   📖 Туториалов: {len(basic_tutorials)} базовых, {len(additional_tutorials)} дополнительных\n\n"
    
    await safe_edit_text(callback.message, text, reply_markup=platform_list_keyboard(platforms))


@router.callback_query(F.data == "admin_platform_add", AdminFilter())
async def platform_add_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало добавления платформы"""
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "➕ <b>Добавление новой платформы</b>\n\n"
        "Введите техническое имя платформы (латиница, без пробелов, например: pc, mobile):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddPlatformStates.waiting_name)


@router.message(AddPlatformStates.waiting_name, AdminFilter())
async def platform_add_name(message: types.Message, state: FSMContext):
    """Ввод технического имени платформы"""
    name = message.text.strip().lower().replace(" ", "_")
    
    # Проверяем, не существует ли уже такая платформа
    existing = await get_platform_by_name(name)
    if existing:
        await message.answer(
            f"❌ Платформа с именем '{name}' уже существует. Введите другое имя:",
            reply_markup=cancel_keyboard()
        )
        return
    
    await state.update_data(name=name)
    await message.answer(
        "Введите отображаемое название платформы (например: 💻 ПК, 📱 Телефоны):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddPlatformStates.waiting_display_name)


@router.message(AddPlatformStates.waiting_display_name, AdminFilter())
async def platform_add_display_name(message: types.Message, state: FSMContext):
    """Ввод отображаемого названия платформы"""
    await state.update_data(display_name=message.text)
    await message.answer(
        "Введите описание платформы (или отправьте /skip для пропуска):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddPlatformStates.waiting_description)


@router.message(AddPlatformStates.waiting_description, AdminFilter())
async def platform_add_description(message: types.Message, state: FSMContext):
    """Ввод описания платформы"""
    description = message.text if message.text != "/skip" else None
    data = await state.get_data()
    
    platform = await create_platform(
        name=data['name'],
        display_name=data['display_name'],
        description=description
    )
    
    await message.answer(
        f"✅ Платформа '{platform.display_name}' успешно создана!",
        reply_markup=platforms_menu()
    )
    await state.clear()


@router.callback_query(F.data.startswith("admin_platform_edit_"), AdminFilter())
async def platform_edit_callback(callback: types.CallbackQuery):
    """Редактирование платформы"""
    await callback.answer()
    platform_id = int(callback.data.split("_")[-1])
    platform = await get_platform_by_id(platform_id)
    
    if not platform:
        await safe_edit_text(
            callback.message,
            "❌ Платформа не найдена",
            reply_markup=platforms_menu()
        )
        return
    
    tutorials = await get_tutorials_by_platform(platform_id)
    basic_tutorials = [t for t in tutorials if t.is_basic]
    additional_tutorials = [t for t in tutorials if not t.is_basic]
    
    text = f"🌐 <b>Платформа: {html.escape(platform.display_name)}</b>\n\n"
    text += f"📝 <b>Техническое имя:</b> {platform.name}\n"
    if platform.description:
        text += f"📋 <b>Описание:</b> {html.escape(platform.description)}\n"
    text += f"📊 <b>Статус:</b> {'✅ Активна' if platform.is_active else '❌ Неактивна'}\n"
    text += f"📖 <b>Туториалов:</b> {len(basic_tutorials)} базовых, {len(additional_tutorials)} дополнительных\n"
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=platform_edit_keyboard(platform_id)
    )


@router.callback_query(F.data.startswith("admin_platform_toggle_"), AdminFilter())
async def platform_toggle_callback(callback: types.CallbackQuery):
    """Переключение статуса платформы"""
    await callback.answer()
    platform_id = int(callback.data.split("_")[-1])
    platform = await get_platform_by_id(platform_id)
    
    if not platform:
        return
    
    await update_platform(platform_id, is_active=not platform.is_active)
    await platform_edit_callback(callback)


@router.callback_query(F.data.startswith("admin_platform_delete_"), AdminFilter())
async def platform_delete_callback(callback: types.CallbackQuery):
    """Удаление платформы"""
    await callback.answer()
    platform_id = int(callback.data.split("_")[-1])
    platform = await get_platform_by_id(platform_id)
    
    if not platform:
        return
    
    # Подтверждение удаления
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data=f"admin_platform_delete_confirm_{platform_id}")
    kb.button(text="❌ Отмена", callback_data=f"admin_platform_edit_{platform_id}")
    kb.adjust(2)
    
    await safe_edit_text(
        callback.message,
        f"⚠️ <b>Подтверждение удаления</b>\n\n"
        f"Вы уверены, что хотите удалить платформу '{html.escape(platform.display_name)}'?\n"
        f"Все туториалы и файлы будут также удалены!",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("admin_platform_delete_confirm_"), AdminFilter())
async def platform_delete_confirm_callback(callback: types.CallbackQuery):
    """Подтверждение удаления платформы"""
    await callback.answer()
    platform_id = int(callback.data.split("_")[-1])
    
    success = await delete_platform(platform_id)
    if success:
        await safe_edit_text(
            callback.message,
            "✅ Платформа успешно удалена",
            reply_markup=platforms_menu()
        )
    else:
        await safe_edit_text(
            callback.message,
            "❌ Ошибка при удалении платформы",
            reply_markup=platforms_menu()
        )


# ========== Управление туториалами ==========

@router.callback_query(F.data.startswith("admin_platform_tutorials_"), AdminFilter())
async def platform_tutorials_callback(callback: types.CallbackQuery):
    """Список туториалов для платформы"""
    await callback.answer()
    platform_id = int(callback.data.split("_")[-1])
    platform = await get_platform_by_id(platform_id)
    
    if not platform:
        return
    
    tutorials = await get_tutorials_by_platform(platform_id)
    
    text = f"📖 <b>Туториалы для платформы: {html.escape(platform.display_name)}</b>\n\n"
    if not tutorials:
        text += "Туториалы не найдены. Добавьте первый туториал!"
    else:
        for tutorial in tutorials:
            tutorial_type = "📘 Базовый" if tutorial.is_basic else "📗 Дополнительный"
            status = "✅" if tutorial.is_active else "❌"
            files_count = len(await get_tutorial_files(tutorial.id))
            text += f"{status} {tutorial_type}: <b>{html.escape(tutorial.title)}</b>\n"
            if tutorial.video_file_id or tutorial.video_note_id:
                text += "   🎥 Видео: есть\n"
            if files_count > 0:
                text += f"   📎 Файлов: {files_count}\n"
            text += "\n"
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=tutorials_list_keyboard(platform_id, tutorials)
    )


@router.callback_query(F.data.startswith("admin_tutorial_add_"), AdminFilter())
async def tutorial_add_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало добавления туториала"""
    await callback.answer()
    platform_id = int(callback.data.split("_")[-1])
    platform = await get_platform_by_id(platform_id)
    
    if not platform:
        return
    
    await state.update_data(platform_id=platform_id)
    await safe_edit_text(
        callback.message,
        f"➕ <b>Добавление туториала для: {html.escape(platform.display_name)}</b>\n\n"
        "Введите заголовок туториала:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddTutorialStates.waiting_title)


@router.message(AddTutorialStates.waiting_title, AdminFilter())
async def tutorial_add_title(message: types.Message, state: FSMContext):
    """Ввод заголовка туториала"""
    await state.update_data(title=message.text)
    await message.answer(
        "Введите текст инструкции (HTML поддерживается, или отправьте /skip для пропуска):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddTutorialStates.waiting_text)


@router.message(AddTutorialStates.waiting_text, AdminFilter())
async def tutorial_add_text(message: types.Message, state: FSMContext):
    """Ввод текста туториала"""
    text = message.text if message.text != "/skip" else None
    data = await state.get_data()
    
    # Спрашиваем, базовый это туториал или дополнительный
    kb = InlineKeyboardBuilder()
    kb.button(text="📘 Базовый", callback_data=f"admin_tutorial_create_basic_{data['platform_id']}")
    kb.button(text="📗 Дополнительный", callback_data=f"admin_tutorial_create_additional_{data['platform_id']}")
    kb.button(text="❌ Отмена", callback_data="cancel")
    kb.adjust(2, 1)
    
    await state.update_data(text=text)
    await message.answer(
        "Выберите тип туториала:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("admin_tutorial_create_basic_"), AdminFilter())
async def tutorial_create_basic(callback: types.CallbackQuery, state: FSMContext):
    """Создание базового туториала"""
    await callback.answer()
    platform_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    
    tutorial = await create_tutorial(
        platform_id=platform_id,
        title=data['title'],
        text=data.get('text'),
        is_basic=True
    )
    
    await safe_edit_text(
        callback.message,
        f"✅ Базовый туториал '{html.escape(tutorial.title)}' успешно создан!\n\n"
        "Теперь вы можете загрузить видео и добавить файлы.",
        reply_markup=tutorial_edit_keyboard(tutorial.id, platform_id)
    )
    await state.clear()


@router.callback_query(F.data.startswith("admin_tutorial_create_additional_"), AdminFilter())
async def tutorial_create_additional(callback: types.CallbackQuery, state: FSMContext):
    """Создание дополнительного туториала"""
    await callback.answer()
    platform_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    
    tutorial = await create_tutorial(
        platform_id=platform_id,
        title=data['title'],
        text=data.get('text'),
        is_basic=False
    )
    
    await safe_edit_text(
        callback.message,
        f"✅ Дополнительный туториал '{html.escape(tutorial.title)}' успешно создан!\n\n"
        "Теперь вы можете загрузить видео и добавить файлы.",
        reply_markup=tutorial_edit_keyboard(tutorial.id, platform_id)
    )
    await state.clear()


# Специфичные обработчики должны быть выше общего обработчика
@router.callback_query(F.data.startswith("admin_tutorial_edit_title_"), AdminFilter())
async def tutorial_edit_title_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования заголовка туториала"""
    await callback.answer()
    tutorial_id = int(callback.data.split("_")[-1])
    
    tutorial = await get_tutorial_by_id(tutorial_id)
    if not tutorial:
        try:
            await callback.message.answer("❌ Туториал не найден")
        except:
            pass
        return
    
    await state.update_data(tutorial_id=tutorial_id)
    try:
        await callback.message.answer(
            f"✏️ <b>Редактирование заголовка</b>\n\n"
            f"Текущий заголовок: <b>{html.escape(tutorial.title)}</b>\n\n"
            "Введите новый заголовок:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        # Если не удалось отправить, пробуем редактировать старое сообщение
        try:
            await safe_edit_text(
                callback.message,
                f"✏️ <b>Редактирование заголовка</b>\n\n"
                f"Текущий заголовок: <b>{html.escape(tutorial.title)}</b>\n\n"
                "Введите новый заголовок:",
                reply_markup=cancel_keyboard()
            )
        except:
            pass
    await state.set_state(EditTutorialStates.waiting_title)


@router.message(EditTutorialStates.waiting_title, AdminFilter())
async def tutorial_save_title(message: types.Message, state: FSMContext):
    """Сохранение нового заголовка туториала"""
    try:
        data = await state.get_data()
        tutorial_id = data['tutorial_id']
        
        new_title = message.text.strip()
        if not new_title:
            await message.answer("❌ Заголовок не может быть пустым. Введите заголовок:")
            return
        
        await update_tutorial(tutorial_id, title=new_title)
        
        tutorial = await get_tutorial_by_id(tutorial_id)
        try:
            await message.answer(
                f"✅ Заголовок успешно изменен на: <b>{html.escape(new_title)}</b>",
                reply_markup=tutorial_edit_keyboard(tutorial_id, tutorial.platform_id),
                parse_mode="HTML"
            )
        except Exception as e:
            try:
                await message.answer(f"✅ Заголовок успешно изменен!")
            except:
                pass
        
        await state.clear()
    except Exception as e:
        await state.clear()
        try:
            await message.answer(f"❌ Ошибка при изменении заголовка: {str(e)}")
        except:
            pass


@router.callback_query(F.data.startswith("admin_tutorial_edit_text_"), AdminFilter())
async def tutorial_edit_text_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования текста туториала"""
    await callback.answer()
    tutorial_id = int(callback.data.split("_")[-1])
    
    tutorial = await get_tutorial_by_id(tutorial_id)
    if not tutorial:
        try:
            await callback.message.answer("❌ Туториал не найден")
        except:
            pass
        return
    
    current_text = tutorial.text or "Текст отсутствует"
    await state.update_data(tutorial_id=tutorial_id)
    try:
        await callback.message.answer(
            f"📝 <b>Редактирование текста</b>\n\n"
            f"Текущий текст:\n{html.escape(current_text[:200])}{'...' if len(current_text) > 200 else ''}\n\n"
            "Введите новый текст (HTML поддерживается, или отправьте /skip для очистки):",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        # Если не удалось отправить, пробуем редактировать старое сообщение
        try:
            await safe_edit_text(
                callback.message,
                f"📝 <b>Редактирование текста</b>\n\n"
                f"Текущий текст:\n{html.escape(current_text[:200])}{'...' if len(current_text) > 200 else ''}\n\n"
                "Введите новый текст (HTML поддерживается, или отправьте /skip для очистки):",
                reply_markup=cancel_keyboard()
            )
        except:
            pass
    await state.set_state(EditTutorialStates.waiting_text)


@router.message(EditTutorialStates.waiting_text, AdminFilter())
async def tutorial_save_text(message: types.Message, state: FSMContext):
    """Сохранение нового текста туториала"""
    try:
        data = await state.get_data()
        tutorial_id = data['tutorial_id']
        
        new_text = None if message.text == "/skip" else message.text
        
        await update_tutorial(tutorial_id, text=new_text)
        
        tutorial = await get_tutorial_by_id(tutorial_id)
        try:
            if new_text:
                await message.answer(
                    f"✅ Текст успешно изменен!\n\n"
                    f"Новый текст:\n{html.escape(new_text[:200])}{'...' if len(new_text) > 200 else ''}",
                    reply_markup=tutorial_edit_keyboard(tutorial_id, tutorial.platform_id),
                    parse_mode="HTML"
                )
            else:
                await message.answer(
                    "✅ Текст успешно очищен!",
                    reply_markup=tutorial_edit_keyboard(tutorial_id, tutorial.platform_id)
                )
        except Exception as e:
            try:
                await message.answer("✅ Текст успешно изменен!")
            except:
                pass
        
        await state.clear()
    except Exception as e:
        await state.clear()
        try:
            await message.answer(f"❌ Ошибка при изменении текста: {str(e)}")
        except:
            pass


# Общий обработчик для просмотра туториала (должен быть ПОСЛЕ специфичных обработчиков)
@router.callback_query(
    F.data.startswith("admin_tutorial_edit_") & 
    ~F.data.contains("_title_") &
    ~F.data.contains("_text_"),
    AdminFilter()
)
async def tutorial_edit_callback(callback: types.CallbackQuery):
    """Редактирование туториала (просмотр)"""
    await callback.answer()
    # Извлекаем ID из callback_data (формат: admin_tutorial_edit_{id})
    parts = callback.data.split("_")
    if len(parts) < 4:
        return
    tutorial_id = int(parts[-1])
    
    tutorial = await get_tutorial_by_id(tutorial_id)
    if not tutorial:
        return
    
    files = await get_tutorial_files(tutorial_id)
    tutorial_type = "📘 Базовый" if tutorial.is_basic else "📗 Дополнительный"
    
    text = f"{tutorial_type} <b>{html.escape(tutorial.title)}</b>\n\n"
    if tutorial.text:
        text += f"📝 <b>Текст:</b> {html.escape(tutorial.text[:100])}{'...' if len(tutorial.text) > 100 else ''}\n"
    if tutorial.video_file_id:
        text += "🎥 <b>Видео:</b> загружено\n"
    if tutorial.video_note_id:
        text += "🎥 <b>Видеосообщение:</b> загружено\n"
    text += f"📎 <b>Файлов:</b> {len(files)}\n"
    text += f"📊 <b>Статус:</b> {'✅ Активен' if tutorial.is_active else '❌ Неактивен'}\n"
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=tutorial_edit_keyboard(tutorial_id, tutorial.platform_id)
    )


@router.callback_query(F.data.startswith("admin_tutorial_upload_video_"), AdminFilter())
async def tutorial_upload_video_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало загрузки видео для туториала"""
    await callback.answer()
    tutorial_id = int(callback.data.split("_")[-1])
    
    await state.update_data(tutorial_id=tutorial_id)
    await safe_edit_text(
        callback.message,
        "🎥 <b>Загрузка видео</b>\n\n"
        "Отправьте видео файл или видеосообщение (круглое видео).\n"
        "Видео будет прикреплено к туториалу.",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddTutorialStates.waiting_video)


@router.message(AddTutorialStates.waiting_video, F.video, AdminFilter())
async def tutorial_receive_video(message: types.Message, state: FSMContext):
    """Получение видео для туториала"""
    try:
        data = await state.get_data()
        tutorial_id = data['tutorial_id']
        
        # Получаем текущий туториал для проверки старого видео
        tutorial = await get_tutorial_by_id(tutorial_id)
        if not tutorial:
            try:
                await message.answer("❌ Туториал не найден")
            except:
                pass
            await state.clear()
            return
        
        video_file_id = message.video.file_id
        
        # Очищаем старое видео (и обычное, и видеосообщение) и сохраняем новое
        await update_tutorial(
            tutorial_id,
            video_file_id=video_file_id,
            video_note_id=None  # Очищаем видеосообщение, если было
        )
        
        tutorial = await get_tutorial_by_id(tutorial_id)
        try:
            await message.answer(
                "✅ Видео успешно загружено! Старое видео удалено.",
                reply_markup=tutorial_edit_keyboard(tutorial_id, tutorial.platform_id)
            )
        except Exception as e:
            # Если не удалось отправить сообщение с клавиатурой, пробуем без нее
            try:
                await message.answer("✅ Видео успешно загружено! Старое видео удалено.")
            except:
                pass  # Игнорируем ошибку, если не удалось отправить
        
        await state.clear()
    except Exception as e:
        await state.clear()
        try:
            await message.answer(f"❌ Ошибка при загрузке видео: {str(e)}")
        except:
            pass


@router.message(AddTutorialStates.waiting_video, F.video_note, AdminFilter())
async def tutorial_receive_video_note(message: types.Message, state: FSMContext):
    """Получение видеосообщения для туториала"""
    try:
        data = await state.get_data()
        tutorial_id = data['tutorial_id']
        
        # Получаем текущий туториал для проверки старого видео
        tutorial = await get_tutorial_by_id(tutorial_id)
        if not tutorial:
            try:
                await message.answer("❌ Туториал не найден")
            except:
                pass
            await state.clear()
            return
        
        video_note_id = message.video_note.file_id
        
        # Очищаем старое видео (и обычное, и видеосообщение) и сохраняем новое
        await update_tutorial(
            tutorial_id,
            video_file_id=None,  # Очищаем обычное видео, если было
            video_note_id=video_note_id
        )
        
        tutorial = await get_tutorial_by_id(tutorial_id)
        try:
            await message.answer(
                "✅ Видеосообщение успешно загружено! Старое видео удалено.",
                reply_markup=tutorial_edit_keyboard(tutorial_id, tutorial.platform_id)
            )
        except Exception as e:
            # Если не удалось отправить сообщение с клавиатурой, пробуем без нее
            try:
                await message.answer("✅ Видеосообщение успешно загружено! Старое видео удалено.")
            except:
                pass  # Игнорируем ошибку, если не удалось отправить
        
        await state.clear()
    except Exception as e:
        await state.clear()
        try:
            await message.answer(f"❌ Ошибка при загрузке видеосообщения: {str(e)}")
        except:
            pass


@router.callback_query(F.data.startswith("admin_tutorial_files_"), AdminFilter())
async def tutorial_files_callback(callback: types.CallbackQuery):
    """Управление файлами туториала"""
    await callback.answer()
    tutorial_id = int(callback.data.split("_")[-1])
    tutorial = await get_tutorial_by_id(tutorial_id)
    
    if not tutorial:
        return
    
    files = await get_tutorial_files(tutorial_id)
    
    text = f"📎 <b>Файлы туториала: {html.escape(tutorial.title)}</b>\n\n"
    if not files:
        text += "Файлы не найдены. Добавьте первый файл!"
    else:
        for file in files:
            file_name = file.file_name or f"Файл #{file.id}"
            text += f"📎 <b>{html.escape(file_name)}</b>\n"
            if file.description:
                text += f"   {html.escape(file.description)}\n"
            text += "\n"
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=tutorial_files_keyboard(tutorial_id, files, tutorial.platform_id)
    )


@router.callback_query(F.data.startswith("admin_tutorial_file_add_"), AdminFilter())
async def tutorial_file_add_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало добавления файла к туториалу"""
    await callback.answer()
    tutorial_id = int(callback.data.split("_")[-1])
    
    await state.update_data(tutorial_id=tutorial_id)
    await safe_edit_text(
        callback.message,
        "📎 <b>Добавление файла</b>\n\n"
        "Отправьте файл (документ, архив, установщик и т.д.).\n"
        "Файл будет прикреплен к туториалу.",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddTutorialFileStates.waiting_file)


@router.message(AddTutorialFileStates.waiting_file, F.document, AdminFilter())
async def tutorial_receive_file(message: types.Message, state: FSMContext):
    """Получение файла для туториала"""
    try:
        data = await state.get_data()
        tutorial_id = data['tutorial_id']
        
        file_id = message.document.file_id
        file_name = message.document.file_name
        file_type = "document"
        
        await add_tutorial_file(
            tutorial_id=tutorial_id,
            file_id=file_id,
            file_name=file_name,
            file_type=file_type
        )
        
        tutorial = await get_tutorial_by_id(tutorial_id)
        files = await get_tutorial_files(tutorial_id)
        
        try:
            await message.answer(
                f"✅ Файл '{html.escape(file_name)}' успешно добавлен!",
                reply_markup=tutorial_files_keyboard(tutorial_id, files, tutorial.platform_id)
            )
        except Exception as e:
            # Если не удалось отправить сообщение, файл все равно сохранен
            # Пытаемся отправить простое сообщение без клавиатуры
            try:
                await message.answer(f"✅ Файл '{html.escape(file_name)}' успешно добавлен!")
            except:
                pass  # Игнорируем ошибку, если не удалось отправить
        
        await state.clear()
    except Exception as e:
        await state.clear()
        try:
            await message.answer(f"❌ Ошибка при добавлении файла: {str(e)}")
        except:
            pass


@router.callback_query(F.data.startswith("admin_tutorial_file_delete_"), AdminFilter())
async def tutorial_file_delete_callback(callback: types.CallbackQuery):
    """Удаление файла туториала"""
    await callback.answer()
    file_id = int(callback.data.split("_")[-1])
    
    # Получаем информацию о файле перед удалением
    from database.base import async_session
    from database.models import TutorialFile
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(
            select(TutorialFile).where(TutorialFile.id == file_id)
        )
        tutorial_file = result.scalar_one_or_none()
        
        if not tutorial_file:
            return
        
        tutorial_id = tutorial_file.tutorial_id
    
    success = await delete_tutorial_file(file_id)
    
    if success:
        tutorial = await get_tutorial_by_id(tutorial_id)
        files = await get_tutorial_files(tutorial_id)
        
        await safe_edit_text(
            callback.message,
            "✅ Файл успешно удален!",
            reply_markup=tutorial_files_keyboard(tutorial_id, files, tutorial.platform_id)
        )
    else:
        await callback.answer("❌ Ошибка при удалении файла", show_alert=True)


@router.callback_query(F.data.startswith("admin_tutorial_toggle_type_"), AdminFilter())
async def tutorial_toggle_type_callback(callback: types.CallbackQuery):
    """Переключение типа туториала (базовый/дополнительный)"""
    await callback.answer()
    tutorial_id = int(callback.data.split("_")[-1])
    tutorial = await get_tutorial_by_id(tutorial_id)
    
    if not tutorial:
        return
    
    await update_tutorial(tutorial_id, is_basic=not tutorial.is_basic)
    await tutorial_edit_callback(callback)


@router.callback_query(F.data.startswith("admin_tutorial_toggle_status_"), AdminFilter())
async def tutorial_toggle_status_callback(callback: types.CallbackQuery):
    """Переключение статуса туториала"""
    await callback.answer()
    tutorial_id = int(callback.data.split("_")[-1])
    tutorial = await get_tutorial_by_id(tutorial_id)
    
    if not tutorial:
        return
    
    await update_tutorial(tutorial_id, is_active=not tutorial.is_active)
    await tutorial_edit_callback(callback)


@router.callback_query(F.data.startswith("admin_tutorial_delete_"), AdminFilter())
async def tutorial_delete_callback(callback: types.CallbackQuery):
    """Удаление туториала"""
    await callback.answer()
    tutorial_id = int(callback.data.split("_")[-1])
    tutorial = await get_tutorial_by_id(tutorial_id)
    
    if not tutorial:
        return
    
    # Подтверждение удаления
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data=f"admin_tutorial_delete_confirm_{tutorial_id}")
    kb.button(text="❌ Отмена", callback_data=f"admin_tutorial_edit_{tutorial_id}")
    kb.adjust(2)
    
    await safe_edit_text(
        callback.message,
        f"⚠️ <b>Подтверждение удаления</b>\n\n"
        f"Вы уверены, что хотите удалить туториал '{html.escape(tutorial.title)}'?\n"
        f"Все файлы будут также удалены!",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("admin_tutorial_delete_confirm_"), AdminFilter())
async def tutorial_delete_confirm_callback(callback: types.CallbackQuery):
    """Подтверждение удаления туториала"""
    await callback.answer()
    tutorial_id = int(callback.data.split("_")[-1])
    tutorial = await get_tutorial_by_id(tutorial_id)
    
    if not tutorial:
        return
    
    platform_id = tutorial.platform_id
    success = await delete_tutorial(tutorial_id)
    
    if success:
        # Обновляем callback.data для правильного вызова
        callback.data = f"admin_platform_tutorials_{platform_id}"
        await platform_tutorials_callback(callback)
    else:
        await callback.answer("❌ Ошибка при удалении туториала", show_alert=True)


# ========== Обработка отмены ==========

@router.callback_query(F.data == "cancel", AdminFilter())
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    """Отмена текущей операции"""
    current_state = await state.get_state()
    
    # Пропускаем состояния рассылки - они обрабатываются в dashboard.py
    if current_state and "BroadcastStates" in current_state:
        return
    
    # Проверяем, что мы находимся в состоянии, связанном с туториалами
    tutorial_states = [
        AddPlatformStates.waiting_name,
        AddPlatformStates.waiting_display_name,
        AddPlatformStates.waiting_description,
        EditPlatformStates.waiting_name,
        EditPlatformStates.waiting_display_name,
        EditPlatformStates.waiting_description,
        AddTutorialStates.waiting_title,
        AddTutorialStates.waiting_text,
        AddTutorialStates.waiting_video,
        EditTutorialStates.waiting_title,
        EditTutorialStates.waiting_text,
        EditTutorialStates.waiting_video,
        AddTutorialFileStates.waiting_file,
    ]
    
    # Если состояние не связано с туториалами, пропускаем обработку
    if current_state not in [str(s) for s in tutorial_states]:
        return
    
    # Обрабатываем отмену для состояний туториалов
    await callback.answer()
    await state.clear()
    await safe_edit_text(
        callback.message,
        "❌ Операция отменена",
        reply_markup=tutorials_menu()
    )


@router.message(F.text == "❌ Отмена", AdminFilter())
async def cancel_message_handler(message: types.Message, state: FSMContext):
    """Обработчик кнопки отмены для сообщений"""
    current_state = await state.get_state()
    
    # Проверяем, что мы находимся в состоянии, связанном с туториалами
    tutorial_states = [
        AddPlatformStates.waiting_name,
        AddPlatformStates.waiting_display_name,
        AddPlatformStates.waiting_description,
        EditPlatformStates.waiting_name,
        EditPlatformStates.waiting_display_name,
        EditPlatformStates.waiting_description,
        AddTutorialStates.waiting_title,
        AddTutorialStates.waiting_text,
        AddTutorialStates.waiting_video,
        EditTutorialStates.waiting_title,
        EditTutorialStates.waiting_text,
        EditTutorialStates.waiting_video,
        AddTutorialFileStates.waiting_file,
    ]
    
    # Если состояние не связано с туториалами, пропускаем обработку
    if current_state not in [str(s) for s in tutorial_states]:
        return
    
    # Обрабатываем отмену для состояний туториалов
    await state.clear()
    try:
        await message.delete()
    except:
        pass
    await message.answer(
        "❌ Операция отменена",
        reply_markup=tutorials_menu()
    )

