"""
Task Manager CLI — Менеджер завдань у командному рядку
=======================================================
A simple command-line task manager that stores tasks in a SQLite database.
Простий менеджер завдань у терміналі зі збереженням у базі даних SQLite.

Usage / Використання:
  python task_manager.py add "Buy groceries"
  python task_manager.py list
  python task_manager.py done 1
  python task_manager.py delete 2
  python task_manager.py clear
"""

import sqlite3
import argparse
import sys
from datetime import datetime


# ─── Database setup / Налаштування бази даних ─────────────────────────────────

DB_FILE = "tasks.db"


def get_connection() -> sqlite3.Connection:
    """
    Open (or create) the SQLite database and return a connection.
    Відкриває або створює базу даних SQLite та повертає з'єднання.
    """
    conn = sqlite3.connect(DB_FILE)
    # Enable foreign keys — useful if you extend the schema later
    # Вмикаємо зовнішні ключі — стане в пригоді при розширенні схеми
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """
    Create the tasks table if it does not exist yet.
    Створює таблицю tasks, якщо вона ще не існує.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            title     TEXT    NOT NULL,
            done      INTEGER NOT NULL DEFAULT 0,   -- 0 = pending, 1 = done / 0 = активне, 1 = виконане
            created   TEXT    NOT NULL               -- ISO-8601 timestamp / мітка часу
        )
    """)
    conn.commit()


# ─── Core operations / Основні операції ───────────────────────────────────────

def add_task(conn: sqlite3.Connection, title: str) -> int:
    """
    Insert a new task and return its auto-generated id.
    Додає нове завдання і повертає його автоматичний id.
    """
    created = datetime.now().isoformat(timespec="seconds")
    cursor = conn.execute(
        "INSERT INTO tasks (title, created) VALUES (?, ?)",
        (title.strip(), created),
    )
    conn.commit()
    return cursor.lastrowid  # id assigned by SQLite / id, призначений SQLite


def list_tasks(conn: sqlite3.Connection, show_done: bool = False) -> list[tuple]:
    """
    Return all tasks. If show_done is False, only pending tasks are returned.
    Повертає всі завдання. Якщо show_done=False — лише незавершені.
    """
    if show_done:
        rows = conn.execute(
            "SELECT id, title, done, created FROM tasks ORDER BY done, id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, title, done, created FROM tasks WHERE done = 0 ORDER BY id"
        ).fetchall()
    return rows


def mark_done(conn: sqlite3.Connection, task_id: int) -> bool:
    """
    Mark a task as completed. Returns True if a row was updated.
    Позначає завдання як виконане. Повертає True, якщо рядок оновлено.
    """
    cursor = conn.execute(
        "UPDATE tasks SET done = 1 WHERE id = ? AND done = 0",
        (task_id,),
    )
    conn.commit()
    # rowcount tells us whether anything actually changed
    # rowcount показує, чи щось реально змінилось
    return cursor.rowcount > 0


def delete_task(conn: sqlite3.Connection, task_id: int) -> bool:
    """
    Permanently remove a task by id. Returns True if deleted.
    Назавжди видаляє завдання за id. Повертає True, якщо видалено.
    """
    cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    return cursor.rowcount > 0


def clear_done(conn: sqlite3.Connection) -> int:
    """
    Delete all completed tasks and return how many were removed.
    Видаляє всі завершені завдання і повертає їх кількість.
    """
    cursor = conn.execute("DELETE FROM tasks WHERE done = 1")
    conn.commit()
    return cursor.rowcount


# ─── Display helpers / Допоміжні функції для виводу ───────────────────────────

CHECKMARK = "✓"
PENDING   = "○"


def print_tasks(rows: list[tuple]) -> None:
    """
    Pretty-print a list of task rows to stdout.
    Красиво виводить список завдань у термінал.
    """
    if not rows:
        print("  (no tasks / завдань немає)")
        return

    for task_id, title, done, created in rows:
        icon   = CHECKMARK if done else PENDING
        status = "done" if done else "pending"
        # Truncate title if it is very long to keep output tidy
        # Скорочуємо назву, якщо вона дуже довга — для охайного вигляду
        short_title = title if len(title) <= 50 else title[:47] + "..."
        print(f"  [{task_id:>3}] {icon}  {short_title:<52}  ({status}, {created})")


# ─── CLI argument parser / Парсер аргументів командного рядка ─────────────────

def build_parser() -> argparse.ArgumentParser:
    """
    Define all sub-commands and their arguments.
    Визначає всі підкоманди та їхні аргументи.
    """
    parser = argparse.ArgumentParser(
        description="CLI Task Manager / Менеджер завдань у терміналі"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add <title>
    p_add = sub.add_parser("add", help="Add a new task / Додати нове завдання")
    p_add.add_argument("title", help="Task description / Опис завдання")

    # list [--all]
    p_list = sub.add_parser("list", help="List tasks / Показати завдання")
    p_list.add_argument(
        "--all", action="store_true",
        help="Include completed tasks / Включити завершені"
    )

    # done <id>
    p_done = sub.add_parser("done", help="Mark task as done / Позначити виконаним")
    p_done.add_argument("id", type=int, help="Task id")

    # delete <id>
    p_del = sub.add_parser("delete", help="Delete a task / Видалити завдання")
    p_del.add_argument("id", type=int, help="Task id")

    # clear
    sub.add_parser("clear", help="Remove all completed tasks / Видалити всі завершені")

    return parser


# ─── Entry point / Точка входу ────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    # All DB work happens inside a 'with' block so the connection closes safely
    # Вся робота з БД відбувається у блоці 'with', щоб з'єднання закривалось надійно
    with get_connection() as conn:
        init_db(conn)

        if args.command == "add":
            new_id = add_task(conn, args.title)
            print(f"✓ Added task #{new_id}: {args.title}")

        elif args.command == "list":
            rows = list_tasks(conn, show_done=args.all)
            label = "All tasks" if args.all else "Pending tasks"
            print(f"\n{label} / Завдання:\n")
            print_tasks(rows)
            print()

        elif args.command == "done":
            if mark_done(conn, args.id):
                print(f"✓ Task #{args.id} marked as done.")
            else:
                print(f"✗ Task #{args.id} not found or already done.", file=sys.stderr)
                sys.exit(1)

        elif args.command == "delete":
            if delete_task(conn, args.id):
                print(f"✓ Task #{args.id} deleted.")
            else:
                print(f"✗ Task #{args.id} not found.", file=sys.stderr)
                sys.exit(1)

        elif args.command == "clear":
            count = clear_done(conn)
            print(f"✓ Removed {count} completed task(s).")


if __name__ == "__main__":
    main()
