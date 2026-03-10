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
    #entries = db.relationship('PersonData', backref='author', lazy=True)  # Изменено здесь!

    # Используем строку для отношения — это предотвращает проблемы с порядком загрузки
    entries = db.relationship('PersonData', backref='author', lazy=True, cascade='all, delete-orphan')

    def is_admin(self):
        """Проверка, является ли пользователь администратором"""
        return self.role == 'admin'

    def can_manage_users(self):
        """Может ли управлять пользователями"""
        return self.is_admin()


class PersonData(db.Model):  # Класс переименован!
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
    category_custom = db.Column(db.String(200))

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
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) #Алиса s

    def __repr__(self):
        return f'<PersonData {self.last_name} {self.first_name}>'
