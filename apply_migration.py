# apply_migration.py
from migrate_new import app
from flask_migrate import upgrade
import os

with app.app_context():
    migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
    print("Применяем все доступные миграции...")
    upgrade(directory=migrations_dir)
    print("✅ Миграции применены")