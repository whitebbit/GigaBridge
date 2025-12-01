# 📋 Шпаргалка: Команды для работы с миграциями

## 🚀 Быстрые команды

### Создание новой миграции (после изменения моделей)

```bash
docker exec -it gigabridge_bot python scripts/migrate.py revision --autogenerate -m "описание изменений"
```

**Примеры:**
```bash
# Добавили новую таблицу
docker exec -it gigabridge_bot python scripts/migrate.py revision --autogenerate -m "add notifications table"

# Добавили поле в существующую таблицу
docker exec -it gigabridge_bot python scripts/migrate.py revision --autogenerate -m "add email field to users"

# Изменили тип поля
docker exec -it gigabridge_bot python scripts/migrate.py revision --autogenerate -m "change user status to enum"
```

### Применение миграций

```bash
docker exec -it gigabridge_bot python scripts/migrate.py upgrade head
```

### Просмотр текущей версии

```bash
docker exec -it gigabridge_bot python scripts/migrate.py current
```

### Просмотр истории миграций

```bash
docker exec -it gigabridge_bot python scripts/migrate.py history
```

### Откат миграции

```bash
# Откатить последнюю миграцию
docker exec -it gigabridge_bot python scripts/migrate.py downgrade -1

# Откатить до конкретной версии
docker exec -it gigabridge_bot python scripts/migrate.py downgrade <revision_id>
```

## 📝 Типичный workflow при добавлении новой таблицы

### 1. Изменить модели в `database/models.py`

```python
class NewTable(Base):
    __tablename__ = "new_table"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    # ... другие поля
```

### 2. Создать миграцию

```bash
docker exec -it gigabridge_bot python scripts/migrate.py revision --autogenerate -m "add new_table"
```

### 3. Проверить созданный файл миграции

Откройте файл в `database/migrations/versions/xxxx_add_new_table.py` и проверьте, что всё правильно.

### 4. Применить миграцию

```bash
docker exec -it gigabridge_bot python scripts/migrate.py upgrade head
```

### 5. Проверить результат

```bash
docker exec -it gigabridge_bot python scripts/migrate.py current
```

## 🔄 Полный цикл работы с миграциями

```bash
# 1. Изменили модели в database/models.py

# 2. Создали миграцию
docker exec -it gigabridge_bot python scripts/migrate.py revision --autogenerate -m "add new feature"

# 3. Проверили файл миграции в database/migrations/versions/

# 4. Применили миграцию
docker exec -it gigabridge_bot python scripts/migrate.py upgrade head

# 5. Проверили текущую версию
docker exec -it gigabridge_bot python scripts/migrate.py current
```

## ⚠️ Важные замечания

1. **Всегда проверяйте** автогенерированные миграции перед применением
2. **Не редактируйте** уже применённые миграции - создавайте новые
3. **Делайте бэкап** перед применением миграций в production
4. **Тестируйте** миграции на тестовой базе данных

## 🆘 Решение проблем

### Ошибка "Target database is not up to date"

```bash
# Применить все миграции
docker exec -it gigabridge_bot python scripts/migrate.py upgrade head
```

### Ошибка "Can't locate revision identified by..."

```bash
# Проверить историю миграций
docker exec -it gigabridge_bot python scripts/migrate.py history
```

### Миграция не видит изменения

Убедитесь, что:
- Все модели импортированы в `database/models.py`
- Модели импортированы в `database/migrations/env.py`
- Используется флаг `--autogenerate`

## 📚 Дополнительная информация

- Полная документация: [MIGRATIONS_README.md](MIGRATIONS_README.md)
- Краткая инструкция: [README_DATABASE.md](README_DATABASE.md)

