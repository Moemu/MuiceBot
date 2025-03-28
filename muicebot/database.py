import asyncio
import json
import os

import aiosqlite
import nonebot_plugin_localstore as store
from nonebot import logger

from ._types import Message


class Database:
    def __init__(self) -> None:
        self.DB_PATH = store.get_plugin_data_dir().joinpath("ChatHistory.db").resolve()

        asyncio.run(self.init_db())

        logger.info(f"数据库路径: {self.DB_PATH}")

    async def init_db(self) -> None:
        """初始化数据库，检查数据库是否存在，不存在则创建"""
        if not os.path.isfile(self.DB_PATH) or self.DB_PATH.stat().st_size == 0:
            logger.info("数据库不存在，正在创建...")
            await self.__create_database()

    def __connect(self) -> aiosqlite.Connection:
        return aiosqlite.connect(self.DB_PATH)

    async def __execute(self, query: str, params=(), fetchone=False, fetchall=False) -> list | None:
        """
        异步执行SQL查询，支持可选参数。

        :param query: 要执行的SQL查询语句
        :param params: 传递给查询的参数
        :param fetchone: 是否获取单个结果
        :param fetchall: 是否获取所有结果
        """
        async with self.__connect() as conn:
            cursor = await conn.cursor()
            await cursor.execute(query, params)
            if fetchone:
                return await cursor.fetchone()  # type: ignore
            if fetchall:
                return await cursor.fetchall()  # type: ignore
            await conn.commit()

        return None

    async def __create_database(self) -> None:
        await self.__execute(
            """CREATE TABLE MSG(
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            TIME TEXT NOT NULL,
            USERID TEXT NOT NULL,
            MESSAGE TEXT NOT NULL,
            RESPOND TEXT NOT NULL,
            HISTORY INTEGER NOT NULL DEFAULT (1),
            IMAGES TEXT NOT NULL DEFAULT "[]");"""
        )

    async def add_item(self, message: Message):
        """
        将消息保存到数据库
        """
        params = (message.time, message.userid, message.message, message.respond, json.dumps(message.images))
        query = """INSERT INTO MSG (TIME, USERID, MESSAGE, RESPOND, IMAGES)
                   VALUES (?, ?, ?, ?, ?)"""
        await self.__execute(query, params)

    async def mark_history_as_unavailable(self, userid: str):
        """
        将用户的所有对话历史标记为不可用 (适用于 reset 命令)

        :userid: 用户id
        """
        query = "UPDATE MSG SET HISTORY = 0 WHERE USERID = ?"
        await self.__execute(query, (userid,))

    async def get_history(self, userid: str, limit: int = 0) -> list[Message]:
        """
        获取用户的所有对话历史，返回一个列表，无结果时返回None

        :userid: 用户id
        :limit: (可选) 返回的最大长度，当该变量设为0时表示全部返回
        """
        if limit:
            query = f"SELECT * FROM MSG WHERE HISTORY = 1 AND USERID = ? ORDER BY ID DESC LIMIT {limit}"
        else:
            query = "SELECT * FROM MSG WHERE HISTORY = 1 AND USERID = ?"
        rows = await self.__execute(query, (userid,), fetchall=True)

        return [Message(*row) for row in rows] if rows else []

    async def remove_last_item(self, userid: str):
        """
        删除用户的最新一条对话历史

        :userid: 用户id
        """
        query = "DELETE FROM MSG WHERE ID = (SELECT ID FROM MSG WHERE USERID = ? ORDER BY ID DESC LIMIT 1)"
        await self.__execute(query, (userid,))
