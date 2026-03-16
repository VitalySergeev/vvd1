# models.py (обновленная версия)
from extensions import db
from flask_login import UserMixin
from datetime import datetime


class User(UserMixin, db.Model):
    """Модель пользователя"""
    __tablename__ = 'users'  # Явно указываем имя таблицы Алиса
    __table_args__ = {'extend_existing': True}  # Добавлено!

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100))
    # Добавляем роль пользователя
    role = db.Column(db.String(20), default='user')

    # Используем строку для отношения — это предотвращает проблемы с порядком загрузки
    entries = db.relationship('PersonData', backref='author', lazy=True, cascade='all, delete-orphan')

    def is_admin(self):
        """Проверка, является ли пользователь администратором"""
        return self.role == 'admin'

    def can_manage_users(self):
        """Может ли управлять пользователями"""
        return self.is_admin()


class PersonData(db.Model):
    """Модель для введенных данных"""
    __tablename__ = 'person_data'  # Новое имя таблицы!
    __table_args__ = {'extend_existing': True}  # Добавлено!

    id = db.Column(db.Integer, primary_key=True)

    # Общие данные
    last_name = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    middle_name = db.Column(db.String(100))
    birth_date = db.Column(db.Date)

    date2 = db.Column(db.Date)
    place2 = db.Column(db.String(255))

    category = db.Column(db.String(200))
    #category_custom = db.Column(db.String(200))

    position = db.Column(db.String(200))
    rank = db.Column(db.String(100))
    number = db.Column(db.String(100))
    lp = db.Column(db.String(255))
    lp_reason = db.Column(db.String(1000))
    place = db.Column(db.String(200))
    ppr = db.Column(db.String(200))
    place2_field = db.Column(db.String(200))
    date4 = db.Column(db.Date)
    ee = db.Column(db.Date)
    ee4 = db.Column(db.Date)

    # Служебные поля
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # ИСПРАВЛЕНО: Убрана связь 'history_entries', оставлена только одна.
    # Связь с историей изменений. backref='record' создаст обратную связь в EditHistory.
    # Параметр 'cascade' гарантирует, что при удалении записи удалится и её история.
    edit_history = db.relationship('EditHistory', backref='record', lazy='dynamic', cascade='all, delete-orphan')

    # Связь с родственниками
    #relatives = db.relationship('Relative', backref='person', lazy=True, cascade='all, delete-orphan')
    # ИЗМЕНЕНО: используем уникальное имя для обратной связи
    relatives_list = db.relationship('Relative', back_populates='main_person', lazy=True, cascade='all, delete-orphan')

def __repr__(self):
        return f'<PersonData {self.last_name} {self.first_name}>'


class EditHistory(db.Model):
    """История редактирования записей"""
    __tablename__ = 'edit_history'

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('person_data.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    field_name = db.Column(db.String(100), nullable=False)  # Какое поле изменили
    old_value = db.Column(db.Text)  # Старое значение
    new_value = db.Column(db.Text)  # Новое значение
    edited_at = db.Column(db.DateTime, default=datetime.now)  # Когда изменили

    # Связи для удобного доступа
    # record = db.relationship('PersonData', backref='history_entries')
    user = db.relationship('User', backref='edit_actions')

    def __repr__(self):
        return f'<EditHistory {self.record_id} {self.field_name} {self.edited_at}>'

class Relative(db.Model):
    """Модель для родственников"""
    __tablename__ = 'relatives'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    person_data_id = db.Column(db.Integer, db.ForeignKey('person_data.id'), nullable=False)

    # Основные данные родственника
    last_name = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    middle_name = db.Column(db.String(100))
    birth_date = db.Column(db.Date)

    # Адреса
    registration_address = db.Column(db.String(500))
    actual_address = db.Column(db.String(500))

    # Контактные данные
    phone = db.Column(db.String(50))

    # Информация о родстве
    relation_degree = db.Column(db.String(100))

    # Дополнительные поля
    size = db.Column(db.String(100))
    period_assignment = db.Column(db.String(200))

    # НОВЫЕ ПОЛЯ: 98 У (П1)
    p1_in_number = db.Column(db.String(200))  # Вх.№
    p1_in_date = db.Column(db.Date)           # Дата вх.
    p1_out_number = db.Column(db.String(200)) # Исх.№
    p1_out_date = db.Column(db.Date)          # Дата исх.
    p1_pay_date = db.Column(db.Date)          # Выпл.

    # НОВЫЕ ПОЛЯ: 755-П2
    p2_in_number = db.Column(db.String(200))
    p2_in_date = db.Column(db.Date)
    p2_out_number = db.Column(db.String(200))
    p2_out_date = db.Column(db.Date)
    p2_pay_date = db.Column(db.Date)

    # НОВЫЕ ПОЛЯ: 665()-П3
    p3_in_number = db.Column(db.String(200))
    p3_in_date = db.Column(db.Date)
    p3_out_number = db.Column(db.String(200))
    p3_out_date = db.Column(db.Date)
    p3_pay_date = db.Column(db.Date)

    # НОВЫЕ ПОЛЯ: ДД-П4
    p4_in_number = db.Column(db.String(200))
    p4_in_date = db.Column(db.Date)
    p4_out_number = db.Column(db.String(200))
    p4_out_date = db.Column(db.Date)
    p4_pay_date = db.Column(db.Date)

    # НОВЫЕ ПОЛЯ: К-П5
    p5_in_number = db.Column(db.String(200))
    p5_in_date = db.Column(db.Date)
    p5_out_number = db.Column(db.String(200))
    p5_out_date = db.Column(db.Date)
    p5_pay_date = db.Column(db.Date)

    # НОВЫЕ ПОЛЯ: Трек-номер
    track_number = db.Column(db.String(200))  # Номер
    track_date = db.Column(db.Date)           # Дата

    # НОВЫЕ ПОЛЯ: Сканы
    scan_number = db.Column(db.String(200))   # №
    scan_date = db.Column(db.Date)            # Дата
    scan_path = db.Column(db.String(500))     # Путь к файлу скана

    # Связь с основной записью
    main_person = db.relationship('PersonData', back_populates='relatives_list')

    # ИСПРАВЛЕНО: Убрана связь 'history_entries', оставлена только одна.
    # Связь с историей изменений. backref='relative_ref' создаст обратную связь в RelativeHistory.
    edit_history = db.relationship('RelativeHistory', backref='relative_ref', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Relative {self.last_name} {self.first_name}>'


class RelativeHistory(db.Model):
    """История редактирования записей родственников"""
    __tablename__ = 'relative_history'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    relative_id = db.Column(db.Integer, db.ForeignKey('relatives.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    field_name = db.Column(db.String(100), nullable=False)
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    edited_at = db.Column(db.DateTime, default=datetime.now)

    # ИСПРАВЛЕНО: Убрана связь 'relative', оставлена только одна ('relative_ref').
    # Связь с пользователем, который сделал изменение.
    user = db.relationship('User', backref='relative_edit_actions')

    def __repr__(self):
        return f'<RelativeHistory {self.relative_id} {self.field_name} {self.edited_at}>'

