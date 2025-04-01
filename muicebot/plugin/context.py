"""
存储并获取 Nonebot 依赖注入中的上下文
"""

from contextvars import ContextVar
from typing import Tuple

from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.typing import T_State

# 定义上下文变量
bot_context: ContextVar[Bot] = ContextVar("bot")
event_context: ContextVar[Event] = ContextVar("event")
state_context: ContextVar[T_State] = ContextVar("state")
mather_context: ContextVar[Matcher] = ContextVar("matcher")


# 获取当前上下文的各种信息
def get_bot() -> Bot:
    return bot_context.get()


def get_event() -> Event:
    return event_context.get()


def get_state() -> T_State:
    return state_context.get()


def get_mather() -> Matcher:
    return mather_context.get()


def set_ctx(bot: Bot, event: Event, state: T_State, matcher: Matcher):
    """
    注册 Nonebot 中的上下文信息
    """
    bot_context.set(bot)
    event_context.set(event)
    state_context.set(state)
    mather_context.set(matcher)


def get_ctx() -> Tuple[Bot, Event, T_State, Matcher]:
    """
    获取当前上下文
    """
    return (get_bot(), get_event(), get_state(), get_mather())
