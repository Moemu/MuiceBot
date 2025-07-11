from nonebot_plugin_orm import Model
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class Msg(Model):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    time: Mapped[str] = mapped_column(String, nullable=False)
    userid: Mapped[str] = mapped_column(String, nullable=False)
    groupid: Mapped[str] = mapped_column(String, nullable=True, default="-1")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    respond: Mapped[str] = mapped_column(Text, nullable=False)
    history: Mapped[int] = mapped_column(Integer, nullable=True, default=1)
    resources: Mapped[str] = mapped_column(Text, nullable=True, default="[]")
    usage: Mapped[int] = mapped_column(Integer, nullable=True, default=-1)
    profile: Mapped[str] = mapped_column(String, nullable=True, default="_default")


class User(Model):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    userid: Mapped[str] = mapped_column(String, nullable=False)
    nickname: Mapped[str] = mapped_column(String, nullable=True, default="_default")
    profile: Mapped[str] = mapped_column(String, nullable=True, default="_default")


class Usage(Model):
    plugin: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
