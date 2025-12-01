from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from database.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    x3ui_id = Column(String, nullable=True)  # ID клиента в 3x-ui (email или UUID)
    plan_id = Column(Integer, ForeignKey("tariffs.id"), nullable=True)
    expire_date = Column(DateTime, nullable=True)
    status = Column(String, default="active")  # active / paused / expired
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
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=True)  # Добавлено для связи с сервером
    yookassa_payment_id = Column(String, nullable=True, unique=True, index=True)  # ID платежа в YooKassa
    status = Column(String, default="pending")  # pending / paid / failed / canceled
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)  # Дата оплаты

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
    is_active = Column(Boolean, default=True)
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
    pbk = Column(String, nullable=True)  # Public Key для Reality (PBK)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)  # Связь с локацией
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    max_users = Column(Integer, nullable=True)
    current_users = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    location = relationship("Location", back_populates="servers")
    subscriptions = relationship("Subscription", back_populates="server")


class Subscription(Base):
    """Подписка пользователя на сервер с тарифом"""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=False)
    x3ui_client_id = Column(String, nullable=True)  # ID клиента в 3x-ui (email или UUID)
    x3ui_client_email = Column(String, nullable=True)  # Email клиента в 3x-ui
    status = Column(String, default="active")  # active / paused / expired
    expire_date = Column(DateTime, nullable=True)
    traffic_used = Column(Float, default=0.0)
    traffic_limit = Column(Float, default=0.0)
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
    is_active = Column(Boolean, default=True)  # Активен ли промокод
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usages = relationship("PromoCodeUsage", back_populates="promo_code")


class PromoCodeUsage(Base):
    """Использование промокода пользователем"""
    __tablename__ = "promo_code_usages"

    id = Column(Integer, primary_key=True, index=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)  # Связь с платежом
    used_at = Column(DateTime, default=datetime.utcnow)

    promo_code = relationship("PromoCode", back_populates="usages")
    user = relationship("User")
    payment = relationship("Payment")


class SupportTicket(Base):
    """Тикет поддержки от пользователя"""
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(String, nullable=False)  # Сообщение пользователя
    status = Column(String, default="open")  # open / answered / closed
    admin_response = Column(String, nullable=True)  # Ответ администратора
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    answered_at = Column(DateTime, nullable=True)  # Дата ответа администратора

    user = relationship("User", back_populates="support_tickets")