import json
from datetime import datetime
from typing import List, Literal, Optional

from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import desc, func, select, update

from ..models import Message, Resource
from .orm_models import Msg, Usage, User


class MessageORM:
    @staticmethod
    def _convert(row: Msg) -> Message:
        """
        反序列化为 Message 实例
        """
        return Message(
            time=row.time,
            userid=row.userid,
            groupid=row.groupid,
            message=row.message,
            respond=row.respond,
            resources=[Resource(**r) for r in json.loads(row.resources or "[]")],
            usage=row.usage,
            profile=row.profile,
        )

    @staticmethod
    async def get_orm_model_by_message(session: async_scoped_session, message: Message) -> Msg:
        """
        通过 Message 获得 ORM 对象
        """
        # 只查三个属性即可
        result = await session.execute(
            select(Msg).where(
                Msg.time == message.time,
                Msg.message == message.message,
                Msg.respond == message.respond,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def add_item(session: async_scoped_session, message: Message):
        """
        将消息保存到数据库
        """
        resources = json.dumps([r.to_dict() for r in message.resources], ensure_ascii=False)
        profile = await UserORM.get_user_profile(session, message.userid)
        session.add(
            Msg(
                time=message.time,
                userid=message.userid,
                groupid=message.groupid,
                message=message.message,
                respond=message.respond,
                resources=resources,
                usage=message.usage,
                profile=profile,
            )
        )

    @staticmethod
    async def get_user_history(session: async_scoped_session, userid: str, limit: int = 0) -> List[Message]:
        """
        获取用户的所有对话历史

        :param userid: 用户名
        :param limit: (可选) 返回的最大长度，当该变量设为0时表示全部返回

        :return: 消息列表
        """
        profile = await UserORM.get_user_profile(session, userid)
        stmt = select(Msg).where(Msg.userid == userid, Msg.history == 1, Msg.profile == profile).order_by(desc(Msg.id))
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [MessageORM._convert(msg) for msg in rows][::-1]

    @staticmethod
    async def get_group_history(session: async_scoped_session, groupid: str, limit: int = 0) -> List[Message]:
        """
        获取群组的所有对话历史，返回一个列表

        :param groupid: 群组id
        :param limit: (可选) 返回的最大长度，当该变量设为0时表示全部返回

        :return: 消息列表
        """
        stmt = select(Msg).where(Msg.groupid == groupid, Msg.history == 1).order_by(desc(Msg.id))
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [MessageORM._convert(msg) for msg in rows][::-1]

    @staticmethod
    async def mark_history_as_unavailable(
        session: async_scoped_session,
        userid: str,
        limit: Optional[int] = None,
    ):
        """
        将用户消息上下文标记为不可用 (适用于 reset 命令)

        :param userid: 用户id
        :param profile: 消息所属存档
        :param limit: (可选)最大操作数
        """
        profile = await UserORM.get_user_profile(session, userid)
        if limit:
            subq = (
                select(Msg.id)
                .where(Msg.userid == userid, Msg.history == 1, Msg.profile == profile)
                .order_by(desc(Msg.id))
                .limit(limit)
            )
            sub_ids = (await session.execute(subq)).scalars().all()
            if sub_ids:
                await session.execute(update(Msg).where(Msg.id.in_(sub_ids)).values(history=0))
        else:
            await session.execute(update(Msg).where(Msg.userid == userid, Msg.profile == profile).values(history=0))

    @staticmethod
    async def get_model_usage(session: async_scoped_session) -> tuple[int, int]:
        """
        获取模型用量数据（今日用量，总用量）

        :return: today_usage, total_usage
        """
        total = await session.execute(select(func.sum(Msg.usage)).where(Msg.usage != -1))
        today = await session.execute(
            select(func.sum(Msg.usage)).where(Msg.usage != -1, Msg.time.like(f"{datetime.now().strftime('%Y.%m.%d')}%"))
        )
        return (today.scalar() or 0), (total.scalar() or 0)

    @staticmethod
    async def get_conv_count(session: async_scoped_session) -> tuple[int, int]:
        """
        获取对话次数（今日次数，总次数）

        :return: today_count, total_count
        """
        total = await session.execute(select(func.count()).where(Msg.usage != -1))
        today = await session.execute(
            select(func.count()).where(Msg.usage != -1, Msg.time.like(f"{datetime.now().strftime('%Y.%m.%d')}%"))
        )
        return (today.scalar() or 0), (total.scalar() or 0)


class UserORM:
    @staticmethod
    async def create_user(session: async_scoped_session, userid: str) -> User:
        user = User(userid=userid)
        session.add(user)
        await session.commit()
        return user

    @staticmethod
    async def get_user(session: async_scoped_session, userid: str) -> User:
        user = await session.execute(select(User).where(User.userid == userid).limit(1))
        return user.scalar_one_or_none() or await UserORM.create_user(session, userid)

    @staticmethod
    async def set_nickname(session: async_scoped_session, userid: str, nickname: str):
        """
        设置用户昵称

        :param userid: 用户id
        :param nickname: 用户昵称
        """
        await session.execute(update(User).where(User.userid == userid).values(nickname=nickname))

    @staticmethod
    async def set_profile(session: async_scoped_session, userid: str, profile: str = "_default"):
        """
        设置消息存档

        :param userid: 用户id
        :param nickname: 消息存档名
        """
        await session.execute(update(User).where(User.userid == userid).values(profile=profile))

    @staticmethod
    async def get_user_profile(session: async_scoped_session, userid: str) -> str:
        result = await session.execute(select(User.profile).where(User.userid == userid).limit(1))
        profile = result.scalar_one_or_none()
        if profile is not None:
            return profile
        await UserORM.create_user(session, userid)
        return "_default"


class UsageORM:
    @staticmethod
    async def get_usage(
        session: async_scoped_session,
        plugin: Optional[str],
        date: Optional[str],
        type: Optional[Literal["chat", "embedding"]] = None,
    ) -> int:
        """
        获取用量信息

        :param session: 数据库会话
        :param plugin: (可选)插件名称，如果为 None 则返回所有插件的用量
        :param date: (可选)日期(`%Y.%m.%d`)，如果为 None 则返回所有日期的用量
        :param type: (可选)用量类型，默认为 None，表示返回所有类型的用量
        """
        query = select(func.sum(Usage.tokens))
        if plugin:
            query = query.where(Usage.plugin == plugin)
        if date:
            query = query.where(Usage.date.like(date))
        if type:
            query = query.where(Usage.type == type)
        result = await session.execute(query)
        return result.scalar() or 0

    @staticmethod
    async def save_usage(
        session: async_scoped_session, plugin: str, total_tokens: int, type: Literal["chat", "embedding"] = "chat"
    ):
        """
        保存用量信息
        """
        if total_tokens < 0:
            return

        date = datetime.now().strftime("%Y.%m.%d")
        stmt = await session.execute(
            select(Usage).where(Usage.plugin == plugin, Usage.type == type, Usage.date == date).limit(1)
        )
        usage = stmt.scalar_one_or_none()

        if usage is not None:
            usage.tokens += total_tokens
            await session.commit()
            return

        session.add(Usage(plugin=plugin, type=type, date=date, tokens=total_tokens))
        await session.commit()
