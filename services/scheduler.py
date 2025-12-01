"""
Централизованный сервис для управления задачами APScheduler
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Настройка планировщика
jobstores = {
    'default': MemoryJobStore()
}

executors = {
    'default': AsyncIOExecutor()
}

job_defaults = {
    'coalesce': True,  # Объединять несколько ожидающих выполнений в одно
    'max_instances': 3,  # Максимальное количество одновременно выполняемых экземпляров задачи
    'misfire_grace_time': 30  # Время в секундах, в течение которого задача может быть выполнена после пропуска
}

scheduler = AsyncIOScheduler(
    jobstores=jobstores,
    executors=executors,
    job_defaults=job_defaults,
    timezone='UTC'
)


def job_listener(event):
    """Слушатель событий задач"""
    if event.exception:
        logger.error(f"Ошибка при выполнении задачи {event.job_id}: {event.exception}")
    else:
        logger.debug(f"Задача {event.job_id} выполнена успешно")


# Добавляем слушатель событий
scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)


def start_scheduler():
    """Запустить планировщик"""
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Планировщик задач запущен")
    else:
        logger.warning("⚠️ Планировщик уже запущен")


def stop_scheduler():
    """Остановить планировщик"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("✅ Планировщик задач остановлен")
    else:
        logger.warning("⚠️ Планировщик не запущен")


def add_job(func, trigger, **kwargs):
    """Добавить задачу в планировщик"""
    job_id = kwargs.pop('id', None)
    if not job_id:
        job_id = f"{func.__name__}_{datetime.now().timestamp()}"
    
    scheduler.add_job(
        func,
        trigger=trigger,
        id=job_id,
        replace_existing=True,
        **kwargs
    )
    logger.info(f"✅ Задача {job_id} добавлена в планировщик")


def remove_job(job_id: str):
    """Удалить задачу из планировщика"""
    try:
        scheduler.remove_job(job_id)
        logger.info(f"✅ Задача {job_id} удалена из планировщика")
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении задачи {job_id}: {e}")


def get_job(job_id: str):
    """Получить информацию о задаче"""
    return scheduler.get_job(job_id)


def get_all_jobs():
    """Получить список всех задач"""
    return scheduler.get_jobs()

