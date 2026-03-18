# check_migration.py
from migrate_new import app
from flask_migrate import current

with app.app_context():
    print("Текущая версия БД:")
    current()