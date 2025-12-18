"""
Сервис для автоматической отправки бэкапов админам
"""
import asyncio
from pathlib import Path
from datetime import datetime
from aiogram.types import FSInputFile
from utils.logger import logger
from utils.db import get_all_admins
from scripts.backup import create_backup
from core.loader import bot


async def send_backup_to_admins():
    """Создает бэкап и отправляет его всем админам"""
    try:
        logger.info("Начало автоматического создания и отправки бэкапа админам")
        
        # Создаем бэкап
        backup_path, error = create_backup()
        
        if error:
            logger.error(f"Ошибка при создании автоматического бэкапа: {error}")
            # Отправляем сообщение об ошибке админам
            admins = await get_all_admins()
            for admin in admins:
                try:
                    await bot.send_message(
                        chat_id=int(admin.tg_id),
                        text=f"❌ <b>Ошибка при создании автоматического бэкапа</b>\n\n{error}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить сообщение об ошибке админу {admin.tg_id}: {e}")
            return
        
        # Получаем информацию о файле
        backup_file = Path(backup_path)
        size_mb = backup_file.stat().st_size / 1024 / 1024
        
        # Получаем всех админов
        admins = await get_all_admins()
        
        if not admins:
            logger.warning("Админы не найдены, бэкап не будет отправлен")
            # Удаляем файл, так как некому отправлять
            try:
                backup_file.unlink()
            except Exception:
                pass
            return
        
        # Отправляем бэкап всем админам
        success_count = 0
        error_count = 0
        
        for admin in admins:
            try:
                file_to_send = FSInputFile(backup_path, filename=backup_file.name)
                await bot.send_document(
                    chat_id=int(admin.tg_id),
                    document=file_to_send,
                    caption=f"📅 <b>Еженедельный бэкап базы данных</b>\n\n"
                           f"📁 Файл: <code>{backup_file.name}</code>\n"
                           f"💾 Размер: {size_mb:.2f} MB\n"
                           f"📅 Дата создания: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                           f"💾 Сохраните этот файл на вашем компьютере.",
                    parse_mode="HTML"
                )
                success_count += 1
                logger.info(f"Бэкап отправлен админу {admin.tg_id}")
                
                # Небольшая задержка между отправками
                await asyncio.sleep(1)
                
            except Exception as e:
                error_count += 1
                logger.error(f"Ошибка при отправке бэкапа админу {admin.tg_id}: {e}")
        
        # Удаляем файл после отправки всем админам
        try:
            backup_file.unlink()
            logger.info(f"Временный файл бэкапа удален: {backup_file.name}")
        except Exception as del_error:
            logger.warning(f"Не удалось удалить временный файл бэкапа: {del_error}")
        
        logger.info(
            f"Автоматическая отправка бэкапа завершена. "
            f"Успешно: {success_count}, Ошибок: {error_count}"
        )
        
    except Exception as e:
        logger.error(f"Критическая ошибка при автоматической отправке бэкапа: {e}", exc_info=True)


def start_weekly_backup():
    """Запускает еженедельную автоматическую отправку бэкапов админам"""
    from services.scheduler import add_job
    
    # Добавляем задачу на каждый понедельник в 3:00 UTC
    add_job(
        send_backup_to_admins,
        trigger="cron",
        day_of_week="mon",
        hour=3,
        minute=0,
        id="weekly_backup_to_admins"
    )
    logger.info("✅ Задача еженедельной отправки бэкапов админам добавлена (каждый понедельник в 3:00 UTC)")

