# migrate_new.py
import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate, init as mg_init, migrate as mg_migrate, upgrade as mg_upgrade
from pathlib import Path

# Определяем папку приложения (работает и для .exe)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Создаем минимальное приложение
app = Flask(__name__)
app.config['SECRET_KEY'] = 'migration-key'

# Настройки БД
DB_PATH = os.path.join(BASE_DIR, 'database', 'app.db')
os.makedirs(os.path.join(BASE_DIR, 'database'), exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Импортируем модели
from models import User, PersonData, EditHistory, Relative, RelativeHistory

# Инициализация
from extensions import db, login_manager

db.init_app(app)
login_manager.init_app(app)

# СОЗДАЕМ ЭКЗЕМПЛЯР MIGRATE (это объект, а не функция)
migrate_instance = Migrate(app, db)


def run_migrations():
    """Запуск миграций"""
    with app.app_context():
        migrations_dir = os.path.join(BASE_DIR, 'migrations')

        if not os.path.exists(migrations_dir):
            print("Инициализация миграций...")
            mg_init(directory=migrations_dir)
            print("✅ Миграции инициализированы")

        print("Создание миграции...")
        # ИСПОЛЬЗУЕМ ПЕРЕИМЕНОВАННУЮ ФУНКЦИЮ
        mg_migrate(directory=migrations_dir, message="автоматическая миграция")
        print("✅ Миграция создана")

        print("Применение миграции...")
        mg_upgrade(directory=migrations_dir)
        print("✅ Миграция применена")


if __name__ == '__main__':
    run_migrations()