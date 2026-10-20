"""Local administrator CLI. Passwords are always entered through hidden prompts."""

from __future__ import annotations

import argparse
import getpass
import sys

from account_store import activate_initial_admin, create_user, disable_user, reset_password
from conversation_store import initialize_database


def _password() -> str:
    first = getpass.getpass("输入密码（至少 12 位，输入不显示）：")
    second = getpass.getpass("再次输入密码：")
    if first != second:
        raise ValueError("两次密码不一致。")
    return first


def main() -> int:
    parser = argparse.ArgumentParser(description="本机邀请制账号管理")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-admin", help="激活初始 admin 账号并接管旧历史")
    create = commands.add_parser("create-user", help="创建试用账号")
    create.add_argument("username")
    reset = commands.add_parser("reset-password", help="重置账号密码并退出该账号全部会话")
    reset.add_argument("username")
    disable = commands.add_parser("disable-user", help="停用试用账号并退出其全部会话")
    disable.add_argument("username")
    args = parser.parse_args()
    try:
        initialize_database()
        if args.command == "init-admin":
            activate_initial_admin(_password())
            print("初始管理员 admin 已激活；旧对话归此账号所有。")
        elif args.command == "create-user":
            create_user(args.username, _password())
            print(f"账号 {args.username} 已创建。")
        elif args.command == "reset-password":
            reset_password(args.username, _password())
            print(f"账号 {args.username} 的密码已更新，旧会话已退出。")
        else:
            disable_user(args.username)
            print(f"账号 {args.username} 已停用，旧会话已退出。")
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"操作失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
