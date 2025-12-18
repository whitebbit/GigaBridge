"""
Обработчики для управления документацией админов
"""
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from utils.filters import AdminFilter
from utils.keyboards.admin_kb import admin_menu, cancel_keyboard
import html
from utils.db import (
    get_all_documentations,
    get_documentation_by_id,
    create_documentation,
    update_documentation,
    delete_documentation,
    get_documentation_files,
    add_documentation_file,
    delete_documentation_file
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from core.loader import bot

router = Router()


async def safe_edit_text(message: types.Message, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения"""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


def documentation_menu():
    """Меню управления документацией"""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить документацию", callback_data="admin_doc_add")
    kb.button(text="📋 Список документаций", callback_data="admin_doc_list")
    kb.button(text="🔙 Назад", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def documentation_list_keyboard(documentations: list):
    """Клавиатура со списком документаций"""
    kb = InlineKeyboardBuilder()
    for doc in documentations:
        kb.button(
            text=f"📄 {doc.title[:40]}",
            callback_data=f"admin_doc_view_{doc.id}"
        )
    kb.button(text="🔙 Назад", callback_data="admin_documentation")
    kb.adjust(1)
    return kb.as_markup()


def documentation_view_keyboard(doc_id: int, has_content: bool = False):
    """Клавиатура для просмотра/редактирования документации"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить заголовок", callback_data=f"admin_doc_edit_title_{doc_id}")
    kb.button(text="📝 Изменить содержимое", callback_data=f"admin_doc_edit_content_{doc_id}")
    if has_content:
        kb.button(text="👁️ Показать полное содержимое", callback_data=f"admin_doc_view_full_{doc_id}")
    kb.button(text="📎 Управлять файлами", callback_data=f"admin_doc_files_{doc_id}")
    kb.button(text="🗑️ Удалить", callback_data=f"admin_doc_delete_{doc_id}")
    kb.button(text="🔙 Назад", callback_data="admin_doc_list")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def documentation_files_keyboard(doc_id: int, files: list):
    """Клавиатура для управления файлами документации"""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить файл", callback_data=f"admin_doc_file_add_{doc_id}")
    
    for file in files:
        file_name = file.file_name or f"Файл #{file.id}"
        file_emoji = {
            "photo": "🖼️",
            "video": "🎥",
            "audio": "🎵",
            "voice": "🎤",
            "video_note": "📹",
            "document": "📎"
        }.get(file.file_type, "📎")
        kb.button(
            text=f"{file_emoji} {file_name[:30]}",
            callback_data=f"admin_doc_file_view_{file.id}"
        )
    
    kb.button(text="🔙 Назад", callback_data=f"admin_doc_view_{doc_id}")
    kb.adjust(1)
    return kb.as_markup()


def documentation_file_view_keyboard(file_id: int, doc_id: int):
    """Клавиатура для просмотра файла"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑️ Удалить файл", callback_data=f"admin_doc_file_delete_{file_id}")
    kb.button(text="🔙 Назад", callback_data=f"admin_doc_files_{doc_id}")
    kb.adjust(1)
    return kb.as_markup()


# ========== States ==========

class AddDocumentationStates(StatesGroup):
    waiting_title = State()
    waiting_content = State()


class EditDocumentationStates(StatesGroup):
    waiting_title = State()
    waiting_content = State()


class AddDocumentationFileStates(StatesGroup):
    waiting_file = State()


# ========== Главное меню документации ==========

@router.callback_query(F.data == "admin_documentation", AdminFilter())
async def documentation_menu_callback(callback: types.CallbackQuery):
    """Меню управления документацией"""
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "📚 <b>Управление документацией</b>\n\n"
        "Здесь вы можете хранить документацию для админов.\n"
        "Выберите действие:",
        reply_markup=documentation_menu()
    )


@router.callback_query(F.data == "admin_doc_list", AdminFilter())
async def documentation_list_callback(callback: types.CallbackQuery):
    """Список всех документаций"""
    await callback.answer()
    documentations = await get_all_documentations()
    
    if not documentations:
        await safe_edit_text(
            callback.message,
            "📋 <b>Список документаций</b>\n\n"
            "Документации не найдены. Добавьте первую документацию!",
            reply_markup=documentation_menu()
        )
        return
    
    text = "📋 <b>Список документаций</b>\n\n"
    for doc in documentations:
        files_count = len(await get_documentation_files(doc.id))
        text += f"📄 <b>{html.escape(doc.title)}</b>\n"
        if doc.content:
            preview = html.escape(doc.content[:50].replace('\n', ' '))
            text += f"   {preview}{'...' if len(doc.content) > 50 else ''}\n"
        if files_count > 0:
            text += f"   📎 Файлов: {files_count}\n"
        text += "\n"
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=documentation_list_keyboard(documentations)
    )


# ========== Добавление документации ==========

@router.callback_query(F.data == "admin_doc_add", AdminFilter())
async def documentation_add_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало добавления документации"""
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "➕ <b>Добавление новой документации</b>\n\n"
        "Введите заголовок документации:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddDocumentationStates.waiting_title)


@router.message(AddDocumentationStates.waiting_title, AdminFilter())
async def documentation_add_title(message: types.Message, state: FSMContext):
    """Ввод заголовка документации"""
    await state.update_data(title=message.text)
    await message.answer(
        "Введите содержимое документации (HTML поддерживается, или отправьте /skip для пропуска):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddDocumentationStates.waiting_content)


@router.message(AddDocumentationStates.waiting_content, AdminFilter())
async def documentation_add_content(message: types.Message, state: FSMContext):
    """Ввод содержимого документации"""
    # Получаем текст с HTML-форматированием, если оно есть
    if message.text == "/skip":
        content = None
    else:
        # Используем html_text для сохранения форматирования из Telegram
        # html_text возвращает текст с HTML-тегами, если форматирование есть
        # Если форматирования нет, используем обычный text
        try:
            content = message.html_text if message.html_text else message.text
        except (AttributeError, TypeError):
            content = message.text or message.caption or ""
    
    data = await state.get_data()
    
    # Получаем ID текущего пользователя
    from utils.db import get_user_by_tg_id
    user = await get_user_by_tg_id(str(message.from_user.id), use_cache=False)
    created_by = user.id if user else None
    
    doc = await create_documentation(
        title=data['title'],
        content=content,
        created_by=created_by
    )
    
    await message.answer(
        f"✅ Документация '{html.escape(doc.title)}' успешно создана!\n\n"
        "Теперь вы можете добавить файлы.",
        reply_markup=documentation_view_keyboard(doc.id, has_content=bool(doc.content))
    )
    await state.clear()


# ========== Просмотр и редактирование документации ==========

@router.callback_query(F.data.startswith("admin_doc_view_full_"), AdminFilter())
async def documentation_view_full_callback(callback: types.CallbackQuery):
    """Просмотр полного содержимого документации"""
    await callback.answer()
    doc_id = int(callback.data.split("_")[-1])
    doc = await get_documentation_by_id(doc_id)
    
    if not doc:
        await callback.answer("❌ Документация не найдена", show_alert=True)
        return
    
    if not doc.content:
        await callback.answer("❌ Содержимое отсутствует", show_alert=True)
        return
    
    files = await get_documentation_files(doc_id)
    
    # Формируем полное сообщение с содержимым и файлами
    text = f"📄 <b>{html.escape(doc.title)}</b>\n\n"
    text += f"{doc.content}\n\n"
    
    # Добавляем информацию о файлах
    if files:
        text += "📎 <b>Прикрепленные файлы:</b>\n"
        for file in files:
            file_emoji = {
                "photo": "🖼️",
                "video": "🎥",
                "audio": "🎵",
                "voice": "🎤",
                "video_note": "📹",
                "document": "📎"
            }.get(file.file_type, "📎")
            file_name = file.file_name or f"Файл #{file.id}"
            text += f"{file_emoji} {html.escape(file_name)}\n"
        text += "\n"
    
    text += f"📅 <b>Создано:</b> {doc.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    if doc.updated_at != doc.created_at:
        text += f"🔄 <b>Обновлено:</b> {doc.updated_at.strftime('%d.%m.%Y %H:%M')}\n"
    
    # Отправляем полное содержимое отдельным сообщением
    # Если содержимое слишком длинное для одного сообщения, разбиваем на части
    max_length = 4000  # Максимальная длина сообщения в Telegram
    
    if len(text) <= max_length:
        # Отправляем одним сообщением
        try:
            await callback.message.answer(
                text,
                parse_mode="HTML"
            )
        except Exception as e:
            await callback.answer(f"❌ Ошибка при отправке: {str(e)[:50]}", show_alert=True)
    else:
        # Сначала отправляем заголовок и метаданные
        header_text = f"📄 <b>{html.escape(doc.title)}</b>\n\n"
        if files:
            header_text += "📎 <b>Прикрепленные файлы:</b>\n"
            for file in files:
                file_emoji = {
                    "photo": "🖼️",
                    "video": "🎥",
                    "audio": "🎵",
                    "voice": "🎤",
                    "video_note": "📹",
                    "document": "📎"
                }.get(file.file_type, "📎")
                file_name = file.file_name or f"Файл #{file.id}"
                header_text += f"{file_emoji} {html.escape(file_name)}\n"
            header_text += "\n"
        header_text += f"📅 <b>Создано:</b> {doc.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        if doc.updated_at != doc.created_at:
            header_text += f"🔄 <b>Обновлено:</b> {doc.updated_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        await callback.message.answer(header_text, parse_mode="HTML")
        
        # Затем отправляем содержимое по частям
        content = doc.content
        part_num = 1
        total_parts = (len(content) + max_length - 1) // max_length
        
        for i in range(0, len(content), max_length):
            part = content[i:i + max_length]
            try:
                await callback.message.answer(
                    f"📄 <b>{html.escape(doc.title)}</b> (часть {part_num}/{total_parts})\n\n"
                    f"{part}",
                    parse_mode="HTML"
                )
            except Exception as e:
                await callback.answer(f"❌ Ошибка при отправке части {part_num}: {str(e)[:50]}", show_alert=True)
                break
            part_num += 1


@router.callback_query(
    F.data.startswith("admin_doc_view_") & ~F.data.startswith("admin_doc_view_full_"),
    AdminFilter()
)
async def documentation_view_callback(callback: types.CallbackQuery):
    """Просмотр информации о документации (краткая информация)"""
    await callback.answer()
    doc_id = int(callback.data.split("_")[-1])
    doc = await get_documentation_by_id(doc_id)
    
    if not doc:
        await safe_edit_text(
            callback.message,
            "❌ Документация не найдена",
            reply_markup=documentation_menu()
        )
        return
    
    files = await get_documentation_files(doc_id)
    
    # Показываем только краткую информацию без превью текста
    text = f"📄 <b>{html.escape(doc.title)}</b>\n\n"
    
    # Информация о содержимом
    if doc.content:
        text += f"📝 <b>Содержимое:</b> {len(doc.content)} символов\n"
    else:
        text += "📝 <b>Содержимое:</b> отсутствует\n"
    
    # Информация о файлах
    text += f"📎 <b>Файлов:</b> {len(files)}\n"
    if files:
        file_types = {}
        for file in files:
            file_type = file.file_type or "unknown"
            file_types[file_type] = file_types.get(file_type, 0) + 1
        file_info = ", ".join([f"{count} {file_type}" for file_type, count in file_types.items()])
        text += f"   Типы: {file_info}\n"
    
    # Даты
    text += f"\n📅 <b>Создано:</b> {doc.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    if doc.updated_at != doc.created_at:
        text += f"🔄 <b>Обновлено:</b> {doc.updated_at.strftime('%d.%m.%Y %H:%M')}\n"
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=documentation_view_keyboard(doc_id, has_content=bool(doc.content))
    )


@router.callback_query(F.data.startswith("admin_doc_edit_title_"), AdminFilter())
async def documentation_edit_title_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования заголовка документации"""
    await callback.answer()
    doc_id = int(callback.data.split("_")[-1])
    
    doc = await get_documentation_by_id(doc_id)
    if not doc:
        try:
            await callback.message.answer("❌ Документация не найдена")
        except:
            pass
        return
    
    await state.update_data(doc_id=doc_id)
    try:
        await callback.message.answer(
            f"✏️ <b>Редактирование заголовка</b>\n\n"
            f"Текущий заголовок: <b>{html.escape(doc.title)}</b>\n\n"
            "Введите новый заголовок:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        try:
            await safe_edit_text(
                callback.message,
                f"✏️ <b>Редактирование заголовка</b>\n\n"
                f"Текущий заголовок: <b>{html.escape(doc.title)}</b>\n\n"
                "Введите новый заголовок:",
                reply_markup=cancel_keyboard()
            )
        except:
            pass
    await state.set_state(EditDocumentationStates.waiting_title)


@router.message(EditDocumentationStates.waiting_title, AdminFilter())
async def documentation_save_title(message: types.Message, state: FSMContext):
    """Сохранение нового заголовка документации"""
    try:
        data = await state.get_data()
        doc_id = data['doc_id']
        
        new_title = message.text.strip()
        if not new_title:
            await message.answer("❌ Заголовок не может быть пустым. Введите заголовок:")
            return
        
        await update_documentation(doc_id, title=new_title)
        
        doc = await get_documentation_by_id(doc_id)
        try:
            await message.answer(
                f"✅ Заголовок успешно изменен на: <b>{html.escape(new_title)}</b>",
                reply_markup=documentation_view_keyboard(doc_id, has_content=True),
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


@router.callback_query(F.data.startswith("admin_doc_edit_content_"), AdminFilter())
async def documentation_edit_content_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования содержимого документации"""
    await callback.answer()
    doc_id = int(callback.data.split("_")[-1])
    
    doc = await get_documentation_by_id(doc_id)
    if not doc:
        try:
            await callback.message.answer("❌ Документация не найдена")
        except:
            pass
        return
    
    current_content = doc.content or "Содержимое отсутствует"
    await state.update_data(doc_id=doc_id)
    try:
        await callback.message.answer(
            f"📝 <b>Редактирование содержимого</b>\n\n"
            f"Текущее содержимое:\n{html.escape(current_content[:200])}{'...' if len(current_content) > 200 else ''}\n\n"
            "Введите новое содержимое (HTML поддерживается, или отправьте /skip для очистки):",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        try:
            await safe_edit_text(
                callback.message,
                f"📝 <b>Редактирование содержимого</b>\n\n"
                f"Текущее содержимое:\n{html.escape(current_content[:200])}{'...' if len(current_content) > 200 else ''}\n\n"
                "Введите новое содержимое (HTML поддерживается, или отправьте /skip для очистки):",
                reply_markup=cancel_keyboard()
            )
        except:
            pass
    await state.set_state(EditDocumentationStates.waiting_content)


@router.message(EditDocumentationStates.waiting_content, AdminFilter())
async def documentation_save_content(message: types.Message, state: FSMContext):
    """Сохранение нового содержимого документации"""
    try:
        data = await state.get_data()
        doc_id = data['doc_id']
        
        # Получаем текст с HTML-форматированием, если оно есть
        if message.text == "/skip":
            new_content = None
        else:
            # Используем html_text для сохранения форматирования из Telegram
            # html_text возвращает текст с HTML-тегами, если форматирование есть
            # Если форматирования нет, используем обычный text
            try:
                new_content = message.html_text if message.html_text else message.text
            except (AttributeError, TypeError):
                new_content = message.text or message.caption or ""
        
        await update_documentation(doc_id, content=new_content)
        
        doc = await get_documentation_by_id(doc_id)
        try:
            if new_content:
                await message.answer(
                    f"✅ Содержимое успешно изменено!\n\n"
                    f"Новое содержимое:\n{html.escape(new_content[:200])}{'...' if len(new_content) > 200 else ''}",
                    reply_markup=documentation_view_keyboard(doc_id, has_content=True),
                    parse_mode="HTML"
                )
            else:
                await message.answer(
                    "✅ Содержимое успешно очищено!",
                    reply_markup=documentation_view_keyboard(doc_id)
                )
        except Exception as e:
            try:
                await message.answer("✅ Содержимое успешно изменено!")
            except:
                pass
        
        await state.clear()
    except Exception as e:
        await state.clear()
        try:
            await message.answer(f"❌ Ошибка при изменении содержимого: {str(e)}")
        except:
            pass


# ========== Управление файлами ==========

@router.callback_query(F.data.startswith("admin_doc_files_"), AdminFilter())
async def documentation_files_callback(callback: types.CallbackQuery):
    """Управление файлами документации"""
    await callback.answer()
    doc_id = int(callback.data.split("_")[-1])
    doc = await get_documentation_by_id(doc_id)
    
    if not doc:
        return
    
    files = await get_documentation_files(doc_id)
    
    text = f"📎 <b>Файлы документации: {html.escape(doc.title)}</b>\n\n"
    if not files:
        text += "Файлы не найдены. Добавьте первый файл!"
    else:
        for file in files:
            file_name = file.file_name or f"Файл #{file.id}"
            file_emoji = {
                "photo": "🖼️",
                "video": "🎥",
                "audio": "🎵",
                "voice": "🎤",
                "video_note": "📹",
                "document": "📎"
            }.get(file.file_type, "📎")
            text += f"{file_emoji} <b>{html.escape(file_name)}</b>\n"
            if file.description:
                text += f"   {html.escape(file.description)}\n"
            text += "\n"
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=documentation_files_keyboard(doc_id, files)
    )


@router.callback_query(F.data.startswith("admin_doc_file_add_"), AdminFilter())
async def documentation_file_add_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало добавления файла к документации"""
    await callback.answer()
    doc_id = int(callback.data.split("_")[-1])
    
    await state.update_data(doc_id=doc_id)
    await safe_edit_text(
        callback.message,
        "📎 <b>Добавление файла</b>\n\n"
        "Отправьте файл (фото, видео, аудио, документ, голосовое сообщение, видеосообщение).\n"
        "Файл будет прикреплен к документации.",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(AddDocumentationFileStates.waiting_file)


@router.message(AddDocumentationFileStates.waiting_file, AdminFilter())
async def documentation_receive_file(message: types.Message, state: FSMContext):
    """Получение файла для документации"""
    try:
        data = await state.get_data()
        doc_id = data['doc_id']
        
        file_id = None
        file_name = None
        file_type = None
        
        # Определяем тип файла и получаем file_id
        if message.photo:
            file_id = message.photo[-1].file_id
            file_type = "photo"
            file_name = "Фото"
        elif message.video:
            file_id = message.video.file_id
            file_type = "video"
            file_name = message.video.file_name or "Видео"
        elif message.audio:
            file_id = message.audio.file_id
            file_type = "audio"
            file_name = message.audio.file_name or "Аудио"
        elif message.voice:
            file_id = message.voice.file_id
            file_type = "voice"
            file_name = "Голосовое сообщение"
        elif message.video_note:
            file_id = message.video_note.file_id
            file_type = "video_note"
            file_name = "Видеосообщение"
        elif message.document:
            file_id = message.document.file_id
            file_type = "document"
            file_name = message.document.file_name or "Документ"
        else:
            await message.answer(
                "❌ Неподдерживаемый тип файла. Отправьте фото, видео, аудио, документ, голосовое или видеосообщение.",
                reply_markup=cancel_keyboard()
            )
            return
        
        await add_documentation_file(
            documentation_id=doc_id,
            file_id=file_id,
            file_name=file_name,
            file_type=file_type
        )
        
        doc = await get_documentation_by_id(doc_id)
        files = await get_documentation_files(doc_id)
        
        try:
            await message.answer(
                f"✅ Файл '{html.escape(file_name)}' успешно добавлен!",
                reply_markup=documentation_files_keyboard(doc_id, files)
            )
        except Exception as e:
            try:
                await message.answer(f"✅ Файл '{html.escape(file_name)}' успешно добавлен!")
            except:
                pass
        
        await state.clear()
    except Exception as e:
        await state.clear()
        try:
            await message.answer(f"❌ Ошибка при добавлении файла: {str(e)}")
        except:
            pass


@router.callback_query(F.data.startswith("admin_doc_file_view_"), AdminFilter())
async def documentation_file_view_callback(callback: types.CallbackQuery):
    """Просмотр файла документации"""
    await callback.answer()
    file_id = int(callback.data.split("_")[-1])
    
    from database.base import async_session
    from database.models import AdminDocumentationFile
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(
            select(AdminDocumentationFile).where(AdminDocumentationFile.id == file_id)
        )
        doc_file = result.scalar_one_or_none()
        
        if not doc_file:
            await callback.answer("❌ Файл не найден", show_alert=True)
            return
        
        doc_id = doc_file.documentation_id
    
    # Отправляем файл пользователю
    try:
        if doc_file.file_type == "photo":
            await bot.send_photo(
                chat_id=callback.from_user.id,
                photo=doc_file.file_id,
                caption=f"📎 {doc_file.file_name or 'Файл'}"
            )
        elif doc_file.file_type == "video":
            await bot.send_video(
                chat_id=callback.from_user.id,
                video=doc_file.file_id,
                caption=f"📎 {doc_file.file_name or 'Видео'}"
            )
        elif doc_file.file_type == "audio":
            await bot.send_audio(
                chat_id=callback.from_user.id,
                audio=doc_file.file_id,
                caption=f"📎 {doc_file.file_name or 'Аудио'}"
            )
        elif doc_file.file_type == "voice":
            await bot.send_voice(
                chat_id=callback.from_user.id,
                voice=doc_file.file_id
            )
        elif doc_file.file_type == "video_note":
            await bot.send_video_note(
                chat_id=callback.from_user.id,
                video_note=doc_file.file_id
            )
        elif doc_file.file_type == "document":
            await bot.send_document(
                chat_id=callback.from_user.id,
                document=doc_file.file_id,
                caption=f"📎 {doc_file.file_name or 'Документ'}"
            )
    except Exception as e:
        await callback.answer(f"❌ Ошибка при отправке файла: {str(e)}", show_alert=True)
        return
    
    # Показываем информацию о файле
    text = f"📎 <b>Файл: {html.escape(doc_file.file_name or 'Без названия')}</b>\n\n"
    text += f"📋 <b>Тип:</b> {doc_file.file_type}\n"
    if doc_file.description:
        text += f"📝 <b>Описание:</b> {html.escape(doc_file.description)}\n"
    
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=documentation_file_view_keyboard(file_id, doc_id)
    )


@router.callback_query(F.data.startswith("admin_doc_file_delete_"), AdminFilter())
async def documentation_file_delete_callback(callback: types.CallbackQuery):
    """Удаление файла документации"""
    await callback.answer()
    file_id = int(callback.data.split("_")[-1])
    
    # Получаем информацию о файле перед удалением
    from database.base import async_session
    from database.models import AdminDocumentationFile
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(
            select(AdminDocumentationFile).where(AdminDocumentationFile.id == file_id)
        )
        doc_file = result.scalar_one_or_none()
        
        if not doc_file:
            return
        
        doc_id = doc_file.documentation_id
    
    success = await delete_documentation_file(file_id)
    
    if success:
        doc = await get_documentation_by_id(doc_id)
        files = await get_documentation_files(doc_id)
        
        await safe_edit_text(
            callback.message,
            "✅ Файл успешно удален!",
            reply_markup=documentation_files_keyboard(doc_id, files)
        )
    else:
        await callback.answer("❌ Ошибка при удалении файла", show_alert=True)


# ========== Удаление документации ==========

@router.callback_query(F.data.startswith("admin_doc_delete_"), AdminFilter())
async def documentation_delete_callback(callback: types.CallbackQuery):
    """Удаление документации"""
    await callback.answer()
    doc_id = int(callback.data.split("_")[-1])
    doc = await get_documentation_by_id(doc_id)
    
    if not doc:
        return
    
    # Подтверждение удаления
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data=f"admin_doc_delete_confirm_{doc_id}")
    kb.button(text="❌ Отмена", callback_data=f"admin_doc_view_{doc_id}")
    kb.adjust(2)
    
    await safe_edit_text(
        callback.message,
        f"⚠️ <b>Подтверждение удаления</b>\n\n"
        f"Вы уверены, что хотите удалить документацию '{html.escape(doc.title)}'?\n"
        f"Все файлы будут также удалены!",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("admin_doc_delete_confirm_"), AdminFilter())
async def documentation_delete_confirm_callback(callback: types.CallbackQuery):
    """Подтверждение удаления документации"""
    await callback.answer()
    doc_id = int(callback.data.split("_")[-1])
    
    success = await delete_documentation(doc_id)
    
    if success:
        await safe_edit_text(
            callback.message,
            "✅ Документация успешно удалена",
            reply_markup=documentation_menu()
        )
    else:
        await callback.answer("❌ Ошибка при удалении документации", show_alert=True)


# ========== Обработка отмены ==========

@router.callback_query(F.data == "cancel", AdminFilter())
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    """Отмена текущей операции"""
    current_state = await state.get_state()
    
    # Пропускаем состояния рассылки - они обрабатываются в dashboard.py
    if current_state and "BroadcastStates" in current_state:
        return
    
    # Проверяем, что мы находимся в состоянии, связанном с документацией
    doc_states = [
        AddDocumentationStates.waiting_title,
        AddDocumentationStates.waiting_content,
        EditDocumentationStates.waiting_title,
        EditDocumentationStates.waiting_content,
        AddDocumentationFileStates.waiting_file,
    ]
    
    # Если состояние не связано с документацией, пропускаем обработку
    if current_state not in [str(s) for s in doc_states]:
        return
    
    # Обрабатываем отмену для состояний документации
    await callback.answer()
    await state.clear()
    await safe_edit_text(
        callback.message,
        "❌ Операция отменена",
        reply_markup=documentation_menu()
    )


@router.message(F.text == "❌ Отмена", AdminFilter())
async def cancel_message_handler(message: types.Message, state: FSMContext):
    """Обработчик кнопки отмены для сообщений"""
    current_state = await state.get_state()
    
    # Проверяем, что мы находимся в состоянии, связанном с документацией
    doc_states = [
        AddDocumentationStates.waiting_title,
        AddDocumentationStates.waiting_content,
        EditDocumentationStates.waiting_title,
        EditDocumentationStates.waiting_content,
        AddDocumentationFileStates.waiting_file,
    ]
    
    # Если состояние не связано с документацией, пропускаем обработку
    if current_state not in [str(s) for s in doc_states]:
        return
    
    # Обрабатываем отмену для состояний документации
    await state.clear()
    try:
        await message.delete()
    except:
        pass
    await message.answer(
        "❌ Операция отменена",
        reply_markup=documentation_menu()
    )

