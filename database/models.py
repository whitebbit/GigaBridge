from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Index, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    email = Column(String, nullable=True)  # Email пользователя для отправки чека от YooKassa
    x3ui_id = Column(String, nullable=True, index=True)  # ID клиента в 3x-ui (email или UUID)
    sub_id = Column(String, nullable=True, index=True)  # SubId для подписок (используется при создании клиентов в 3x-ui)
    plan_id = Column(Integer, ForeignKey("tariffs.id"), nullable=True)
    expire_date = Column(DateTime, nullable=True, index=True)
    status = Column(String, default="active", index=True)  # active / paused / expired
    traffic_used = Column(Float, default=0.0)
    traffic_limit = Column(Float, default=0.0)
    is_admin = Column(Boolean, default=False)
    used_first_purchase_discount = Column(Boolean, default=False)  # Использовал ли пользователь скидку на первую покупку
    created_at = Column(DateTime, default=datetime.utcnow)

    payments = relationship("Payment", back_populates="user")
    plan = relationship("Tariff", back_populates="users")  # Deprecated: используйте subscriptions
    subscriptions = relationship("Subscription", back_populates="user")
    support_tickets = relationship("SupportTicket", back_populates="user")

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(String, ForeignKey("users.tg_id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="RUB")  # Изменено с USD на RUB
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=True, index=True)  # Добавлено для связи с сервером
    yookassa_payment_id = Column(String, nullable=True, unique=True, index=True)  # ID платежа в YooKassa
    status = Column(String, default="pending", index=True)  # pending / paid / failed / canceled
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    paid_at = Column(DateTime, nullable=True, index=True)  # Дата оплаты

    user = relationship("User", back_populates="payments")
    tariff = relationship("Tariff", back_populates="payments")

class Tariff(Base):
    __tablename__ = "tariffs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    duration_days = Column(Integer, nullable=False)
    traffic_limit = Column(Float, default=0.0)

    users = relationship("User", back_populates="plan")  # Deprecated: используйте subscriptions
    payments = relationship("Payment", back_populates="tariff")
    subscriptions = relationship("Subscription", back_populates="tariff")

class Location(Base):
    """Локация для группировки серверов"""
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)  # Название локации (например, "Москва", "Санкт-Петербург")
    description = Column(String, nullable=True)
    price = Column(Float, nullable=False)  # Цена для этой локации (одинаковая для всех серверов в локации)
    is_active = Column(Boolean, default=True, index=True)
    is_hidden = Column(Boolean, default=False, index=True)  # Скрыта ли локация от пользователей (не отображается в списке для продажи)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    servers = relationship("Server", back_populates="location")


class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    api_url = Column(String, nullable=False)  # Полный URL панели управления 3x-ui (например, http://89.169.7.60:30648/rolDT4Th57aiCxNzOi)
    api_username = Column(String, nullable=False)  # Имя пользователя для входа в панель
    api_password = Column(String, nullable=False)  # Пароль для входа в панель
    ssl_certificate = Column(Text, nullable=True)  # SSL сертификат (.crt) для проверки сертификата API
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)  # Связь с локацией
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    max_users = Column(Integer, nullable=True)
    current_users = Column(Integer, default=0)
    payment_expire_date = Column(DateTime, nullable=True, index=True)  # Дата окончания оплаты сервера
    payment_days = Column(Integer, nullable=True)  # Количество дней, на которое куплен сервер
    sub_url = Column(String, nullable=True)  # URL для генерации ссылок подписки (формат: {sub_url}/{subID})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    location = relationship("Location", back_populates="servers")
    subscriptions = relationship("Subscription", back_populates="server")


class Subscription(Base):
    """Подписка пользователя на сервер с тарифом"""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False, index=True)
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=False)
    x3ui_client_id = Column(String, nullable=True, index=True)  # ID клиента в 3x-ui (email или UUID)
    x3ui_client_email = Column(String, nullable=True, index=True)  # Email клиента в 3x-ui
    sub_id = Column(String, nullable=True, index=True)  # Уникальный SubId для этой подписки (отличается от user.sub_id)
    location_unique_name = Column(String, nullable=True, index=True)  # Уникальное название локации для этой подписки (создается при создании)
    status = Column(String, default="active", index=True)  # active / paused / expired
    expire_date = Column(DateTime, nullable=True, index=True)
    traffic_used = Column(Float, default=0.0)
    traffic_limit = Column(Float, default=0.0)
    is_private = Column(Boolean, default=False, index=True)  # Безграничная подписка (бессрочная, не проверяется на удаление и активность)
    notification_3_days_sent = Column(Boolean, default=False)  # Отправлено ли уведомление за 3 дня
    notification_1_day_sent = Column(Boolean, default=False)  # Отправлено ли уведомление за 1 день
    notification_deletion_warning_1_sent = Column(Boolean, default=False)  # Отправлено ли первое предупреждение о предстоящем удалении
    notification_deletion_warning_2_sent = Column(Boolean, default=False)  # Отправлено ли второе предупреждение о предстоящем удалении
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")
    server = relationship("Server", back_populates="subscriptions")
    tariff = relationship("Tariff", back_populates="subscriptions")


class PromoCode(Base):
    """Промокод для скидок"""
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, nullable=False, unique=True, index=True)  # Код промокода
    discount_percent = Column(Float, nullable=False)  # Процент скидки
    max_uses = Column(Integer, nullable=True)  # Максимальное количество использований (None = безлимитный)
    current_uses = Column(Integer, default=0)  # Текущее количество использований
    allow_reuse_by_same_user = Column(Boolean, default=False)  # Разрешить многократное использование одним пользователем
    is_active = Column(Boolean, default=True)  # Активен ли промокод
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usages = relationship("PromoCodeUsage", back_populates="promo_code")


class PromoCodeUsage(Base):
    """Использование промокода пользователем"""
    __tablename__ = "promo_code_usages"

    id = Column(Integer, primary_key=True, index=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True, index=True)  # Связь с платежом
    used_at = Column(DateTime, default=datetime.utcnow)

    promo_code = relationship("PromoCode", back_populates="usages")
    user = relationship("User")
    payment = relationship("Payment")


class SupportTicket(Base):
    """Тикет поддержки от пользователя"""
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)  # Сообщение пользователя (Text для поддержки больших сообщений)
    photo_file_id = Column(String, nullable=True)  # file_id изображения в Telegram (если прикреплено)
    status = Column(String, default="open", index=True)  # open / answered / closed
    admin_response = Column(String, nullable=True)  # Ответ администратора
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    answered_at = Column(DateTime, nullable=True)  # Дата ответа администратора

    user = relationship("User", back_populates="support_tickets")


class Platform(Base):
    """Платформа для инструкций (PC, Mobile, и т.д.)"""
    __tablename__ = "platforms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)  # Название платформы (например, "PC", "Mobile")
    display_name = Column(String, nullable=False)  # Отображаемое название (например, "💻 ПК", "📱 Телефоны")
    description = Column(String, nullable=True)  # Описание платформы
    is_active = Column(Boolean, default=True, index=True)
    order = Column(Integer, default=0)  # Порядок отображения
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tutorials = relationship("Tutorial", back_populates="platform", cascade="all, delete-orphan")


class Tutorial(Base):
    """Туториал/инструкция для платформы"""
    __tablename__ = "tutorials"

    id = Column(Integer, primary_key=True, index=True)
    platform_id = Column(Integer, ForeignKey("platforms.id"), nullable=False, index=True)
    title = Column(String, nullable=False)  # Заголовок туториала
    text = Column(Text, nullable=True)  # Текст инструкции (HTML поддерживается)
    video_file_id = Column(String, nullable=True)  # file_id видео в Telegram
    video_note_id = Column(String, nullable=True)  # file_id видеосообщения (круглое видео) в Telegram
    is_basic = Column(Boolean, default=True, index=True)  # Базовый туториал (True) или дополнительный (False)
    order = Column(Integer, default=0)  # Порядок отображения
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    platform = relationship("Platform", back_populates="tutorials")
    files = relationship("TutorialFile", back_populates="tutorial", cascade="all, delete-orphan")


class TutorialFile(Base):
    """Файл, прикрепленный к туториалу (установщик, документ, архив и т.д.)"""
    __tablename__ = "tutorial_files"

    id = Column(Integer, primary_key=True, index=True)
    tutorial_id = Column(Integer, ForeignKey("tutorials.id"), nullable=False, index=True)
    file_id = Column(String, nullable=False)  # file_id файла в Telegram
    file_name = Column(String, nullable=True)  # Имя файла для отображения
    file_type = Column(String, nullable=True)  # Тип файла (document, photo, video, и т.д.)
    description = Column(String, nullable=True)  # Описание файла
    order = Column(Integer, default=0)  # Порядок отображения
    created_at = Column(DateTime, default=datetime.utcnow)

    tutorial = relationship("Tutorial", back_populates="files")


class FailedSubscriptionAttempt(Base):
    """Неудачные попытки создания подписки после успешной оплаты"""
    __tablename__ = "failed_subscription_attempts"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True, index=True)  # Для продления
    is_renewal = Column(Boolean, default=False, index=True)  # Это продление существующей подписки?
    error_message = Column(Text, nullable=False)  # Сообщение об ошибке
    error_type = Column(String, nullable=True)  # Тип ошибки (api_error, database_error, etc.)
    attempt_count = Column(Integer, default=0)  # Количество попыток обработки
    max_attempts = Column(Integer, default=5)  # Максимальное количество попыток
    next_attempt_at = Column(DateTime, nullable=True, index=True)  # Когда попробовать снова
    status = Column(String, default="pending", index=True)  # pending / processing / completed / failed / refunded
    refund_attempted = Column(Boolean, default=False)  # Была ли попытка возврата средств
    refund_id = Column(String, nullable=True)  # ID возврата в YooKassa
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)  # Когда была завершена обработка

    payment = relationship("Payment")
    user = relationship("User")
    server = relationship("Server")
    subscription = relationship("Subscription")


# Составные индексы для оптимизации частых запросов
Index('idx_subscription_user_status', Subscription.user_id, Subscription.status)
Index('idx_subscription_server_status', Subscription.server_id, Subscription.status)
Index('idx_subscription_status_expire', Subscription.status, Subscription.expire_date)
Index('idx_payment_status_created', Payment.status, Payment.created_at)
Index('idx_payment_tg_status', Payment.tg_id, Payment.status)
Index('idx_tutorial_platform_active', Tutorial.platform_id, Tutorial.is_active)
Index('idx_tutorial_platform_basic', Tutorial.platform_id, Tutorial.is_basic)
Index('idx_failed_attempt_status_next', FailedSubscriptionAttempt.status, FailedSubscriptionAttempt.next_attempt_at)
Index('idx_failed_attempt_payment', FailedSubscriptionAttempt.payment_id, FailedSubscriptionAttempt.status)