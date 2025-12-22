"""
Обработчик команд для управления обновлениями из GitHub
"""
import os
import sys
import subprocess
from pathlib import Path
from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.filters import AdminFilter
from utils.keyboards.admin_kb import admin_menu, cancel_keyboard
from utils.logger import logger

router = Router()

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent.parent.parent


class UpdateStates(StatesGroup):
    """Состояния для обновления из GitHub"""
    waiting_confirm = State()


async def safe_edit_text(message: types.Message, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения с обработкой ошибок"""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "message can't be edited" in error_msg or "message is not modified" in error_msg:
            try:
                await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            except Exception:
                pass
        else:
            raise


def run_git_command(command: list, cwd: str = None) -> tuple[bool, str, str]:
    """
    Выполняет git команду и возвращает результат
    
    Returns:
        (success: bool, stdout: str, stderr: str)
    """
    try:
        if cwd is None:
            cwd = str(project_root)
        
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Команда превысила время ожидания (30 секунд)"
    except Exception as e:
        return False, "", str(e)


def check_git_repo() -> tuple[bool, str]:
    """Проверяет, является ли директория git репозиторием"""
    success, stdout, stderr = run_git_command(["git", "rev-parse", "--git-dir"])
    if success:
        return True, "Git репозиторий обнаружен"
    else:
        return False, f"Директория не является git репозиторием: {stderr}"


def get_git_status() -> tuple[bool, str]:
    """Получает статус git репозитория"""
    # Проверяем, есть ли изменения
    success, stdout, stderr = run_git_command(["git", "status", "--porcelain"])
    if not success:
        return False, f"Ошибка при проверке статуса: {stderr}"
    
    has_changes = bool(stdout.strip())
    
    # Получаем текущую ветку
    success, branch, _ = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if not success:
        branch = "неизвестно"
    
    # Получаем последний коммит
    success, commit, _ = run_git_command(["git", "log", "-1", "--format=%h - %s (%ar)", "HEAD"])
    if not success:
        commit = "неизвестно"
    else:
        commit = commit.strip()
    
    # Проверяем, настроен ли удаленный репозиторий
    success, remote, _ = run_git_command(["git", "remote", "get-url", "origin"])
    has_remote = success and remote.strip()
    
    # Получаем информацию о расхождении с origin (если удаленный репозиторий настроен)
    ahead_count = "0"
    behind_count = "0"
    
    if has_remote:
        # Получаем имя текущей ветки
        success, current_branch, _ = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if success and current_branch.strip():
            branch_name = current_branch.strip()
            remote_branch = f"origin/{branch_name}"
            
            # Проверяем, существует ли удаленная ветка
            success, _, _ = run_git_command(["git", "rev-parse", "--verify", remote_branch])
            if success:
                # Получаем количество коммитов впереди
                success, ahead, _ = run_git_command(["git", "rev-list", "--count", "HEAD", f"^{remote_branch}"])
                ahead_count = ahead.strip() if success and ahead.strip().isdigit() else "0"
                
                # Получаем количество коммитов позади
                success, behind, _ = run_git_command(["git", "rev-list", "--count", remote_branch, "^HEAD"])
                behind_count = behind.strip() if success and behind.strip().isdigit() else "0"
    
    status_text = f"📋 <b>Статус Git репозитория</b>\n\n"
    status_text += f"🌿 <b>Ветка:</b> {branch}\n"
    status_text += f"📝 <b>Последний коммит:</b> {commit}\n\n"
    
    if has_changes:
        status_text += "⚠️ <b>Есть незакоммиченные изменения!</b>\n"
        status_text += "Рекомендуется закоммитить или сохранить изменения перед обновлением.\n\n"
    
    if not has_remote:
        status_text += "⚠️ <b>Удаленный репозиторий не настроен</b>\n"
        status_text += "Для использования обновлений настройте origin:\n"
        status_text += "<code>git remote add origin <url></code>\n"
    elif behind_count != "0":
        status_text += f"⬇️ <b>Доступно обновлений:</b> {behind_count} коммит(ов)\n"
    else:
        status_text += "✅ <b>Репозиторий актуален</b> (нет новых обновлений)\n"
    
    if ahead_count != "0":
        status_text += f"⬆️ <b>Локальных коммитов:</b> {ahead_count}\n"
    
    return True, status_text


def get_git_log(count: int = 5) -> str:
    """Получает последние коммиты"""
    success, stdout, stderr = run_git_command([
        "git", "log", 
        f"-{count}", 
        "--format=%h - %s (%an, %ar)",
        "HEAD"
    ])
    
    if not success:
        return f"Ошибка при получении лога: {stderr}"
    
    if not stdout.strip():
        return "Нет коммитов"
    
    log_text = "📜 <b>Последние коммиты:</b>\n\n"
    for line in stdout.strip().split('\n'):
        log_text += f"• {line}\n"
    
    return log_text


def pull_updates() -> tuple[bool, str]:
    """Выполняет git pull для получения обновлений"""
    # Сначала делаем fetch
    success, stdout, stderr = run_git_command(["git", "fetch"])
    if not success:
        return False, f"Ошибка при fetch: {stderr}"
    
    # Затем делаем pull
    success, stdout, stderr = run_git_command(["git", "pull"])
    if not success:
        return False, f"Ошибка при pull: {stderr}"
    
    output = stdout.strip() if stdout else ""
    if "Already up to date" in output:
        return True, "✅ Репозиторий уже актуален. Обновлений нет."
    
    return True, f"✅ Обновления успешно загружены!\n\n{output}"


@router.callback_query(F.data == "admin_updates", AdminFilter())
async def updates_menu(callback: types.CallbackQuery):
    """Меню управления обновлениями"""
    await callback.answer()
    
    # Проверяем, является ли директория git репозиторием
    is_repo, repo_message = check_git_repo()
    if not is_repo:
        await callback.message.answer(
            f"❌ <b>Ошибка</b>\n\n{repo_message}\n\n"
            "Для использования обновлений из GitHub необходимо, чтобы проект был git репозиторием.",
            reply_markup=admin_menu(),
            parse_mode="HTML"
        )
        return
    
    # Получаем статус
    success, status_text = get_git_status()
    if not success:
        await callback.message.answer(
            f"❌ <b>Ошибка при получении статуса</b>\n\n{status_text}",
            reply_markup=admin_menu(),
            parse_mode="HTML"
        )
        return
    
    # Получаем последние коммиты
    log_text = get_git_log(3)
    
    text = f"{status_text}\n{log_text}\n"
    text += "Выберите действие:"
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Проверить обновления", callback_data="updates_check")
    kb.button(text="⬇️ Загрузить обновления", callback_data="updates_pull")
    kb.button(text="📜 История коммитов", callback_data="updates_log")
    kb.button(text="🔙 Назад", callback_data="admin_menu")
    kb.adjust(1)
    
    await safe_edit_text(callback.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "updates_check", AdminFilter())
async def check_updates(callback: types.CallbackQuery):
    """Проверка наличия обновлений"""
    await callback.answer("⏳ Проверка обновлений...")
    
    # Делаем fetch для получения информации об обновлениях
    success, stdout, stderr = run_git_command(["git", "fetch"])
    if not success:
        await callback.message.answer(
            f"❌ <b>Ошибка при проверке обновлений</b>\n\n{stderr}",
            parse_mode="HTML"
        )
        return
    
    # Получаем обновленный статус
    success, status_text = get_git_status()
    if not success:
        await callback.message.answer(
            f"❌ <b>Ошибка</b>\n\n{status_text}",
            parse_mode="HTML"
        )
        return
    
    # Проверяем, есть ли обновления
    success, current_branch, _ = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    behind_count = "0"
    
    if success and current_branch.strip():
        branch_name = current_branch.strip()
        remote_branch = f"origin/{branch_name}"
        
        # Проверяем, существует ли удаленная ветка
        success, _, _ = run_git_command(["git", "rev-parse", "--verify", remote_branch])
        if success:
            success, behind, _ = run_git_command(["git", "rev-list", "--count", remote_branch, "^HEAD"])
            behind_count = behind.strip() if success and behind.strip().isdigit() else "0"
    
    if behind_count == "0":
        text = f"{status_text}\n\n✅ <b>Обновлений нет. Репозиторий актуален.</b>"
    else:
        # Получаем список новых коммитов
        success, current_branch, _ = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        commits = ""
        
        if success and current_branch.strip():
            branch_name = current_branch.strip()
            remote_branch = f"origin/{branch_name}"
            
            success, commits, _ = run_git_command([
                "git", "log", 
                f"HEAD..{remote_branch}",
                "--format=%h - %s (%an, %ar)",
                "--oneline"
            ])
        
        text = f"{status_text}\n\n"
        if success and commits.strip():
            text += "📋 <b>Новые коммиты:</b>\n"
            for line in commits.strip().split('\n')[:10]:  # Показываем до 10 коммитов
                text += f"• {line}\n"
            if commits.count('\n') >= 10:
                text += "...\n"
        text += "\n⬇️ Нажмите 'Загрузить обновления' для применения изменений."
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    if behind_count != "0":
        kb.button(text="⬇️ Загрузить обновления", callback_data="updates_pull")
    kb.button(text="🔄 Обновить статус", callback_data="updates_check")
    kb.button(text="🔙 Назад", callback_data="admin_updates")
    kb.adjust(1)
    
    await safe_edit_text(callback.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "updates_pull", AdminFilter())
async def pull_updates_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик загрузки обновлений"""
    await callback.answer()
    
    # Проверяем наличие незакоммиченных изменений
    success, stdout, _ = run_git_command(["git", "status", "--porcelain"])
    has_changes = success and bool(stdout.strip())
    
    if has_changes:
        # Показываем предупреждение
        text = "⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        text += "Обнаружены незакоммиченные изменения в репозитории.\n"
        text += "При загрузке обновлений возможны конфликты.\n\n"
        text += "Рекомендуется:\n"
        text += "1. Закоммитить изменения\n"
        text += "2. Или сохранить их в stash\n\n"
        text += "Продолжить загрузку обновлений?"
        
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Да, продолжить", callback_data="updates_pull_confirm")
        kb.button(text="❌ Отмена", callback_data="admin_updates")
        kb.adjust(1)
        
        await safe_edit_text(callback.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await state.set_state(UpdateStates.waiting_confirm)
    else:
        # Загружаем обновления сразу
        await execute_pull(callback.message)


@router.callback_query(F.data == "updates_pull_confirm", UpdateStates.waiting_confirm, AdminFilter())
async def pull_updates_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение загрузки обновлений"""
    await callback.answer()
    await state.clear()
    await execute_pull(callback.message)


async def execute_pull(message: types.Message):
    """Выполняет загрузку обновлений"""
    status_msg = await message.answer(
        "⏳ <b>Загрузка обновлений...</b>\n\n"
        "Пожалуйста, подождите...",
        parse_mode="HTML"
    )
    
    success, result = pull_updates()
    
    if success:
        text = f"✅ <b>Обновления загружены!</b>\n\n{result}\n\n"
        text += "⚠️ <b>Важно:</b> Для применения изменений может потребоваться перезапуск бота.\n"
        text += "Если были изменены зависимости, выполните:\n"
        text += "<code>pip install -r requirements.txt</code>"
    else:
        text = f"❌ <b>Ошибка при загрузке обновлений</b>\n\n{result}"
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Проверить обновления", callback_data="updates_check")
    kb.button(text="🔙 Назад", callback_data="admin_updates")
    kb.adjust(1)
    
    await safe_edit_text(status_msg, text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "updates_log", AdminFilter())
async def show_log(callback: types.CallbackQuery):
    """Показывает историю коммитов"""
    await callback.answer()
    
    log_text = get_git_log(10)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить", callback_data="updates_log")
    kb.button(text="🔙 Назад", callback_data="admin_updates")
    kb.adjust(1)
    
    await safe_edit_text(callback.message, log_text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "cancel", UpdateStates.waiting_confirm, AdminFilter())
async def cancel_update(callback: types.CallbackQuery, state: FSMContext):
    """Отмена загрузки обновлений"""
    await callback.answer()
    await state.clear()
    
    await safe_edit_text(
        callback.message,
        "❌ Загрузка обновлений отменена.",
        reply_markup=admin_menu()
    )

