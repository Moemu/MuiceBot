import base64
import os
import ssl
import sys
import time
from typing import Optional

import httpx
import nonebot_plugin_localstore as store
from nonebot import get_bot, logger
from nonebot.adapters import Event, MessageSegment
from nonebot.adapters.onebot.v11 import Bot as Onebotv11Bot
from nonebot.adapters.onebot.v12 import Bot as Onebotv12Bot
from nonebot.adapters.onebot.v12.exception import UnsupportedParam
from nonebot.adapters.telegram import Event as TelegramEvent
from nonebot.adapters.telegram.message import File as TelegramFile
from nonebot.log import default_filter, logger_id

from ..config import plugin_config

IMG_DIR = store.get_plugin_data_dir() / ".cache" / "images"
IMG_DIR.mkdir(parents=True, exist_ok=True)

User_Agent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    "AppleWebKit/537.36 (KHTML, like Gecko)"
    "Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0"
)


async def save_image_as_file(
    image_url: str, file_name: str = str(time.time_ns()) + ".jpg", proxy: Optional[str] = None
) -> str:
    """
    保存图片至本地目录

    :image_url: 图片在线地址
    :file_name: 要保存的文件名
    :proxy: 代理地址

    :return: 保存后的本地目录
    """
    ssl_context = ssl.create_default_context()
    ssl_context.set_ciphers("DEFAULT")

    async with httpx.AsyncClient(proxy=proxy, verify=ssl_context) as client:
        r = await client.get(image_url, headers={"User-Agent": User_Agent})
        local_path = (IMG_DIR / file_name).resolve()
        with open(local_path, "wb") as file:
            file.write(r.content)
        return str(local_path)


async def save_image_as_base64(image_url: str, proxy: Optional[str] = None) -> str:
    """
    从在线 url 获取图像 Base64

    :image_url: 图片在线地址
    :return: 本地地址
    """
    ssl_context = ssl.create_default_context()
    ssl_context.set_ciphers("DEFAULT")

    async with httpx.AsyncClient(proxy=proxy, verify=ssl_context) as client:
        r = await client.get(image_url, headers={"User-Agent": User_Agent})
        image_base64 = base64.b64encode(r.content)
    return image_base64.decode("utf-8")


async def legacy_get_images(message: MessageSegment, event: Event) -> str:
    """
    传统模式获取图片

    :return: 本地地址
    """
    bot = get_bot()

    if isinstance(bot, Onebotv12Bot):
        if message.type == "image":
            try:
                image_path = await bot.get_file(type="url", file_id=message.data["file_id"])
            except UnsupportedParam as e:
                logger.error(f"Onebot 实现不支持获取文件 URL，图片获取操作失败：{e}")
                return ""

            return str(image_path)

    elif isinstance(bot, Onebotv11Bot):
        if message.type == "image" and "url" in message.data and "file" in message.data:
            return await save_image_as_file(message.data["url"], message.data["file"])

    elif isinstance(event, TelegramEvent):
        if isinstance(message, TelegramFile):
            file_id = message.data["file"]
            file = await bot.get_file(file_id=file_id)
            if not file.file_path:
                return ""
            url = f"https://api.telegram.org/file/bot{bot.bot_config.token}/{file.file_path}"  # type: ignore
            filename = file.file_path.split("/")[1]
            return await save_image_as_file(url, filename, proxy=plugin_config.telegram_proxy)

    return ""


def init_logger():
    console_handler_level = plugin_config.log_level

    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.mkdir(log_dir)

    log_file_path = f"{log_dir}/{time.strftime('%Y-%m-%d')}.log"

    # 移除 NoneBot 默认的日志处理器
    logger.remove(logger_id)
    # 添加新的日志处理器
    logger.add(
        sys.stdout,
        level=console_handler_level,
        diagnose=True,
        format="<lvl>[{level}] {function}: {message}</lvl>",
        filter=default_filter,
        colorize=True,
    )

    logger.add(
        log_file_path,
        level="DEBUG",
        format="[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {function}: {message}",
        encoding="utf-8",
        rotation="1 day",
        retention="7 days",
    )
