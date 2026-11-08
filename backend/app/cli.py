import getpass
import argparse
from argon2 import PasswordHasher
from sqlalchemy import delete
from .db import Session, Admin, AdminSession

parser = argparse.ArgumentParser()
parser.add_argument('command', choices=['init-admin', 'reset-password'])
args = parser.parse_args()
with Session.begin() as db:
    admin = db.get(Admin, 1)
    if args.command == 'init-admin' and admin:
        raise SystemExit('管理员已存在；重置请使用 reset-password')
    username = admin.username if admin else input('账号: ').strip()
    password = getpass.getpass('密码（至少12位）: ')
    if len(password) < 12 or password != getpass.getpass('再次输入: '):
        raise SystemExit('密码不符合要求或不一致')
    if not admin:
        admin = Admin(id=1, username=username)
        db.add(admin)
    admin.password_hash = PasswordHasher().hash(password)
    db.execute(delete(AdminSession))
print('管理员已保存，旧会话已失效')
