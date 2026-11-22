"""Stockage SQLite des chapitres du lore, un registre par serveur Discord."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Chapter:
    id: int
    number: int
    title: str
    text: str
    raw_input: str
    author_id: int
    author_name: str
    created_at: str


class LoreStore:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chapters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                number      INTEGER NOT NULL,
                title       TEXT    NOT NULL,
                text        TEXT    NOT NULL,
                raw_input   TEXT    NOT NULL,
                author_id   INTEGER NOT NULL,
                author_name TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                UNIQUE (guild_id, number)
            )
            """
        )
        self.conn.commit()

    @staticmethod
    def _row(row: sqlite3.Row) -> Chapter:
        return Chapter(
            id=row["id"],
            number=row["number"],
            title=row["title"],
            text=row["text"],
            raw_input=row["raw_input"],
            author_id=row["author_id"],
            author_name=row["author_name"],
            created_at=row["created_at"],
        )

    def all_chapters(self, guild_id: int) -> list[Chapter]:
        rows = self.conn.execute(
            "SELECT * FROM chapters WHERE guild_id = ? ORDER BY number", (guild_id,)
        ).fetchall()
        return [self._row(r) for r in rows]

    def get_chapter(self, guild_id: int, number: int) -> Chapter | None:
        row = self.conn.execute(
            "SELECT * FROM chapters WHERE guild_id = ? AND number = ?", (guild_id, number)
        ).fetchone()
        return self._row(row) if row else None

    def add_chapter(
        self,
        guild_id: int,
        title: str,
        text: str,
        raw_input: str,
        author_id: int,
        author_name: str,
    ) -> Chapter:
        with self.conn:
            (next_number,) = self.conn.execute(
                "SELECT COALESCE(MAX(number), 0) + 1 FROM chapters WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self.conn.execute(
                """
                INSERT INTO chapters
                    (guild_id, number, title, text, raw_input, author_id, author_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, next_number, title, text, raw_input, author_id, author_name, created_at),
            )
        chapter = self.get_chapter(guild_id, next_number)
        assert chapter is not None
        return chapter

    def delete_last(self, guild_id: int) -> Chapter | None:
        chapters = self.all_chapters(guild_id)
        if not chapters:
            return None
        last = chapters[-1]
        with self.conn:
            self.conn.execute("DELETE FROM chapters WHERE id = ?", (last.id,))
        return last
