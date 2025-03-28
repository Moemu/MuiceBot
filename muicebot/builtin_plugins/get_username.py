from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import Bot as Onebotv11Bot
from nonebot.adapters.onebot.v12 import Bot as Onebotv12Bot
from nonebot.adapters.qq import Event as QQEvent
from nonebot.adapters.telegram import Event as TelegramEvent

from muicebot.plugin import PluginMetadata
from muicebot.plugin.func_call import on_function_call

__metadata__ = PluginMetadata(
    name="get_username", description="获取用户名的插件", usage="直接调用，返回当前对话的用户名"
)


@on_function_call(description="获取当前对话的用户名字")
async def get_username(bot: Bot, event: Event) -> str:
    userid = event.get_user_id()
    username = ""

    if isinstance(bot, Onebotv12Bot):
        userinfo = await bot.get_user_info(user_id=userid)
        username = userinfo.get("user_displayname", userid)

    elif isinstance(bot, Onebotv11Bot):
        userinfo = await bot.get_stranger_info(user_id=int(userid))
        username = userinfo.get("user_displayname", userid)

    elif isinstance(event, TelegramEvent):
        username = event.chat.username  # type: ignore
        if not username:
            first_name = event.from_.first_name  # type: ignore
            last_name = event.from_.last_name  # type: ignore
            username = f"{first_name if first_name else ''} {last_name if last_name else ''}".strip()

    elif isinstance(event, QQEvent):
        username = event.member.nick  # type: ignore

    if not username:
        username = userid

    return username
