"""
Обработчик команд для управления бэкапами базы данных
"""
import os
import sys
from pathlib import Path
from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile
from utils.filters import AdminFilter
from utils.keyboards.admin_kb import admin_menu, cancel_keyboard
from utils.logger import logger

router = Router()


async def safe_edit_text(message: types.Message, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения с обработкой ошибок"""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        # Если сообщение не может быть отредактировано, отправляем новое
        if "message can't be edited" in error_msg or "message is not modified" in error_msg:
            # Пытаемся отправить новое сообщение
            try:
                await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            except Exception:
                pass  # Игнорируем, если не удалось отправить
        else:
            raise

# Добавляем корневую директорию проекта в PYTHONPATH для импорта скриптов
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class RestoreStates(StatesGroup):
    """Состояния для восстановления бэкапа"""
    waiting_backup_file = State()  # Ожидание файла бэкапа от админа для восстановления


@router.callback_query(F.data == "admin_backup", AdminFilter())
async def backup_menu(callback: types.CallbackQuery):
    """Меню управления бэкапами"""
    await callback.answer()
    
    text = "💾 <b>Управление бэкапами</b>\n\n"
    text += "📦 Бэкапы не сохраняются на сервере.\n"
    text += "Файл бэкапа отправляется вам для сохранения на вашем компьютере.\n\n"
    text += "Выберите действие:"
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="💾 Создать бэкап", callback_data="backup_create")
    kb.button(text="🔄 Восстановить из бэкапа", callback_data="backup_restore")
    kb.button(text="🔙 Назад", callback_data="admin_menu")
    kb.adjust(1)
    
    await safe_edit_text(callback.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "backup_create", AdminFilter())
async def create_backup(callback: types.CallbackQuery):
    """Создание нового бэкапа"""
    await callback.answer("⏳ Создание бэкапа...")
    
    try:
        # Импортируем функцию создания бэкапа
        from scripts.backup import create_backup
        
        backup_path, error = create_backup()
        
        if error:
            await callback.message.answer(
                f"❌ <b>Ошибка при создании бэкапа</b>\n\n{error}",
                parse_mode="HTML"
            )
            return
        
        # Получаем информацию о файле
        backup_file = Path(backup_path)
        size_mb = backup_file.stat().st_size / 1024 / 1024
        
        # Отправляем файл админу одним сообщением
        try:
            file_to_send = FSInputFile(backup_path, filename=backup_file.name)
            await callback.message.answer_document(
                document=file_to_send,
                caption=f"✅ <b>Бэкап базы данных успешно создан!</b>\n\n"
                       f"📁 Файл: <code>{backup_file.name}</code>\n"
                       f"💾 Размер: {size_mb:.2f} MB\n\n"
                       f"💾 Сохраните этот файл на вашем компьютере.\n"
                       f"Бэкап не сохраняется на сервере.",
                parse_mode="HTML"
            )
            
            # Удаляем файл с сервера после успешной отправки
            try:
                backup_file.unlink()
                logger.info(f"Временный файл бэкапа удален: {backup_file.name}")
            except Exception as del_error:
                logger.warning(f"Не удалось удалить временный файл бэкапа: {del_error}")
                
        except Exception as send_error:
            logger.error(f"Ошибка при отправке файла бэкапа: {send_error}", exc_info=True)
            # Если файл слишком большой (>50MB), сообщаем об этом
            if size_mb > 50:
                await callback.message.answer(
                    f"❌ <b>Файл слишком большой</b>\n\n"
                    f"Размер: {size_mb:.2f} MB\n"
                    f"Лимит Telegram: 50 MB\n\n"
                    f"Используйте создание бэкапа через командную строку:\n"
                    f"<code>python scripts/backup.py</code>",
                    parse_mode="HTML"
                )
            else:
                await callback.message.answer(
                    f"❌ <b>Ошибка при отправке файла</b>\n\n{str(send_error)}",
                    parse_mode="HTML"
                )
            
            # Удаляем файл даже при ошибке
            try:
                backup_file.unlink()
            except Exception:
                pass
        
    except Exception as e:
        logger.error(f"Ошибка при создании бэкапа: {e}", exc_info=True)
        await callback.message.answer(
            f"❌ <b>Ошибка при создании бэкапа</b>\n\n{str(e)}",
            parse_mode="HTML"
        )


@router.callback_query(F.data == "backup_restore", AdminFilter())
async def restore_backup_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало процесса восстановления бэкапа"""
    await callback.answer()
    
    await callback.message.answer(
        "🔄 <b>ВОССТАНОВЛЕНИЕ ИЗ БЭКАПА</b>\n\n"
        "🔴 <b>ВНИМАНИЕ!</b>\n\n"
        "Восстановление бэкапа <b>ПЕРЕЗАПИШЕТ</b> все текущие данные в базе данных!\n\n"
        "Отправьте файл бэкапа (формат .tar.gz) для восстановления.\n\n"
        "Это действие <b>НЕОБРАТИМО</b>!",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    
    await state.set_state(RestoreStates.waiting_backup_file)


@router.message(RestoreStates.waiting_backup_file, F.document, AdminFilter())
async def restore_backup_execute(message: types.Message, state: FSMContext):
    """Восстановление базы данных из загруженного файла бэкапа"""
    try:
        document = message.document
        
        # Проверяем формат файла
        if not document.file_name or not document.file_name.endswith('.tar.gz'):
            await message.answer(
                "❌ <b>Неверный формат файла</b>\n\n"
                "Файл должен быть в формате .tar.gz\n\n"
                "Попробуйте еще раз или отмените операцию.",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
            return
        
        # Проверяем размер файла (максимум 500MB для безопасности)
        file_size_mb = document.file_size / 1024 / 1024
        if file_size_mb > 500:
            await message.answer(
                f"❌ <b>Файл слишком большой</b>\n\n"
                f"Размер: {file_size_mb:.2f} MB\n"
                f"Максимальный размер: 500 MB\n\n"
                "Попробуйте еще раз или отмените операцию.",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
            return
        
        # Создаем временную директорию для бэкапа
        import shutil
        temp_dir = project_root / "backups" / "temp_restore"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем файл
        status_msg = await message.answer(
            "⏳ <b>Загрузка и восстановление бэкапа...</b>\n\n"
            "Пожалуйста, подождите. Это может занять некоторое время...",
            parse_mode="HTML"
        )
        
        # Скачиваем файл
        from core.loader import bot
        file_info = await bot.get_file(document.file_id)
        
        # Генерируем имя временного файла
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"restore_{timestamp}.tar.gz"
        backup_path = temp_dir / backup_filename
        
        # Скачиваем файл
        await bot.download_file(file_info.file_path, destination=str(backup_path))
        
        # Проверяем, что файл успешно скачан
        if not backup_path.exists() or backup_path.stat().st_size == 0:
            await safe_edit_text(
                status_msg,
                "❌ <b>Ошибка при загрузке файла</b>\n\n"
                "Файл не был загружен. Попробуйте еще раз.",
                parse_mode="HTML"
            )
            return
        
        # Восстанавливаем базу данных
        try:
            from scripts.restore import restore_backup
            
            success, restore_message = restore_backup(str(backup_path), confirm=True)
            
            if success:
                await safe_edit_text(
                    status_msg,
                    f"✅ <b>Бэкап успешно восстановлен!</b>\n\n"
                    f"📁 Файл: <code>{document.file_name}</code>\n"
                    f"💾 Размер: {file_size_mb:.2f} MB\n\n"
                    f"{restore_message}",
                    parse_mode="HTML"
                )
            else:
                await safe_edit_text(
                    status_msg,
                    f"❌ <b>Ошибка при восстановлении</b>\n\n{restore_message}",
                    parse_mode="HTML"
                )
        except Exception as restore_error:
            logger.error(f"Ошибка при восстановлении бэкапа: {restore_error}", exc_info=True)
            await safe_edit_text(
                status_msg,
                f"❌ <b>Ошибка при восстановлении бэкапа</b>\n\n{str(restore_error)}",
                parse_mode="HTML"
            )
        finally:
            # Удаляем временный файл
            try:
                if backup_path.exists():
                    backup_path.unlink()
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                logger.info("Временные файлы восстановления удалены")
            except Exception as del_error:
                logger.warning(f"Не удалось удалить временные файлы: {del_error}")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка при восстановлении бэкапа: {e}", exc_info=True)
        await message.answer(
            f"❌ <b>Ошибка при восстановлении бэкапа</b>\n\n{str(e)}\n\n"
            "Попробуйте еще раз или отмените операцию.",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "cancel", RestoreStates.waiting_backup_file, AdminFilter())
async def restore_backup_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Отмена восстановления бэкапа"""
    await callback.answer()
    await state.clear()
    
    await safe_edit_text(
        callback.message,
        "❌ Восстановление бэкапа отменено.",
        reply_markup=admin_menu()
    )

