import re
import time
from datetime import timedelta
from pathlib import Path

import nonebot_plugin_localstore as store
from arclet.alconna import Alconna, AllParam, Args
from nonebot import (
    get_adapters,
    get_bot,
    get_driver,
    logger,
    on_message,
)
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot.typing import T_State
from nonebot_plugin_alconna import (
    AlconnaMatch,
    CommandMeta,
    Match,
    MsgTarget,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_alconna.uniseg import Image, UniMsg
from nonebot_plugin_session import SessionIdType, extract_session

from .config import plugin_config
from .muice import Muice
from .plugin import get_plugins, load_plugins, set_ctx
from .scheduler import setup_scheduler
from .utils.SessionManager import SessionManager
from .utils.utils import get_version, legacy_get_images, save_image_as_file

COMMAND_PREFIXES = [".", "/"]

muice = Muice()
scheduler = None
START_TIME = time.time()
connect_time = 0.0
session_manager = SessionManager()

muice_nicknames = plugin_config.muice_nicknames
regex_patterns = [f"^{re.escape(nick)}\\s*" for nick in muice_nicknames]
combined_regex = "|".join(regex_patterns)

driver = get_driver()
adapters = get_adapters()


@driver.on_startup
async def load_bot():
    logger.info(f"MuiceBot 版本: {get_version()}")
    logger.info(f"MuiceBot 数据目录: {store.get_plugin_data_dir().resolve()}")
    logger.info("加载 MuiceBot 框架...")

    logger.info(f"加载模型适配器: {muice.model_loader} ...")
    if not muice.load_model():
        logger.error("模型加载失败，请检查配置项是否正确")
        exit(1)
    logger.success(f"模型适配器加载成功: {muice.model_loader} ⭐")

    logger.info("加载 MuiceBot 插件...")
    for plugin_dir in plugin_config.plugins_dir:
        load_plugins(plugin_dir)

    if plugin_config.enable_builtin_plugins:
        logger.info("加载 MuiceBot 内嵌插件...")
        builtin_plugins_path = Path(__file__).parent / "builtin_plugins"
        muicebot_plugins_path = Path(__file__).resolve().parent.parent
        load_plugins(builtin_plugins_path, base_path=muicebot_plugins_path)

    logger.success("插件加载完成⭐")

    logger.success("MuiceBot 已准备就绪✨")


@driver.on_bot_connect
async def bot_connected():
    logger.success("Bot 已连接，消息处理进程开始运行✨")
    global connect_time
    if not connect_time:
        connect_time = time.time()


command_about = on_alconna(
    Alconna(COMMAND_PREFIXES, "about", meta=CommandMeta("输出关于信息")),
    priority=90,
    block=True,
)

command_help = on_alconna(
    Alconna(COMMAND_PREFIXES, "help", meta=CommandMeta("输出帮助信息")),
    priority=90,
    block=True,
)

command_status = on_alconna(
    Alconna(COMMAND_PREFIXES, "status", meta=CommandMeta("显示当前状态")),
    priority=90,
    block=True,
)

command_reset = on_alconna(
    Alconna(COMMAND_PREFIXES, "reset", meta=CommandMeta("清空对话记录")),
    priority=10,
    block=True,
)

command_refresh = on_alconna(
    Alconna(COMMAND_PREFIXES, "refresh", meta=CommandMeta("刷新模型输出")),
    priority=10,
    block=True,
)

command_undo = on_alconna(
    Alconna(COMMAND_PREFIXES, "undo", meta=CommandMeta("撤回上一个对话")),
    priority=10,
    block=True,
)

command_load = on_alconna(
    Alconna(
        COMMAND_PREFIXES,
        "load",
        Args["config_name", str, ""],
        meta=CommandMeta("加载模型", usage="load <config_name>", example="load model.deepseek"),
    ),
    priority=10,
    block=True,
    permission=SUPERUSER,
)

command_schedule = on_alconna(
    Alconna(COMMAND_PREFIXES, "schedule", meta=CommandMeta("加载定时任务")),
    priority=10,
    block=True,
    permission=SUPERUSER,
)

command_start = on_alconna(
    Alconna(COMMAND_PREFIXES, "start", meta=CommandMeta("Telegram 的启动指令")),
    priority=10,
    block=True,
)

command_whoami = on_alconna(
    Alconna(COMMAND_PREFIXES, "whoami", meta=CommandMeta("输出当前用户信息")),
    priority=90,
    block=True,
)

nickname_event = on_alconna(
    Alconna(re.compile(combined_regex), Args["text?", AllParam], separators=""),
    priority=99,
    block=True,
)

at_event = on_message(priority=100, rule=to_me(), block=True)


@driver.on_bot_connect
@command_schedule.handle()
async def on_bot_connect():
    global scheduler
    if not scheduler:
        scheduler = setup_scheduler(muice, get_bot())


@driver.on_bot_disconnect
async def on_bot_disconnect():
    global scheduler
    if scheduler:
        scheduler.remove_all_jobs()
        scheduler = None


@command_help.handle()
async def handle_command_help():
    await command_help.finish(
        "基本命令：\n"
        "about 获取关于信息\n"
        "help 输出此帮助信息\n"
        "status 显示当前状态\n"
        "refresh 刷新模型输出\n"
        "reset 清空对话记录\n"
        "undo 撤回上一个对话\n"
        "whoami 输出当前用户信息\n"
        "load <config_name> 加载模型\n"
        "（支持的命令前缀：“.”、“/”）"
    )


@command_about.handle()
async def handle_command_about():
    model_loader = muice.model_loader
    # plugins_list = ", ".join(get_available_plugin_names())
    mplugins_list = ", ".join(get_plugins())

    model_name = muice.model_config.model_name if muice.model_config.model_name else "Unknown"
    is_multimodal = "是" if muice.multimodal else "否"

    if scheduler and scheduler.running:
        job_ids = [job.id for job in scheduler.get_jobs()]
        if job_ids:
            current_scheduler = ", ".join(job_ids)
        else:
            current_scheduler = "无"
    else:
        current_scheduler = "无(调度器未启动)"

    await command_about.finish(
        f"框架版本: {get_version()}\n"
        f"已加载的 Muicebot 插件: {mplugins_list}\n"
        f"\n"
        f"模型: {model_name}({model_loader})\n"
        f"多模态: {is_multimodal}\n"
        f"\n"
        f"定时任务: {current_scheduler}"
    )


@command_status.handle()
async def handle_command_status():
    now = time.time()
    uptime = timedelta(seconds=int(now - START_TIME))
    bot_uptime = timedelta(seconds=int(now - connect_time))

    model_status = "运行中" if muice.model and muice.model.is_running else "未启动"
    today_usage, total_usage = await muice.database.get_model_usage()

    scheduler_status = "运行中" if scheduler and scheduler.running else "未启动"

    await command_status.finish(
        f"框架已运行: {str(uptime)}\n"
        f"bot已稳定连接: {str(bot_uptime)}\n"
        f"\n"
        f"模型加载器状态: {model_status}\n"
        f"今日模型用量: {today_usage} tokens (总 {total_usage} tokens)\n "
        f"\n"
        f"定时任务调度器状态: {scheduler_status}\n"
    )


@command_reset.handle()
async def handle_command_reset(event: Event):
    userid = event.get_user_id()
    response = await muice.reset(userid)
    await command_reset.finish(response)


@command_refresh.handle()
async def handle_command_refresh(event: Event):
    userid = event.get_user_id()
    response = await muice.refresh(userid)

    if isinstance(response, str):
        paragraphs = response.split("\n\n")

        for index, paragraph in enumerate(paragraphs):
            if index == len(paragraphs) - 1:
                await command_refresh.finish(paragraph)
            await command_refresh.send(paragraph)

        return

    current_paragraph = ""

    async for chunk in response:
        current_paragraph += chunk
        paragraphs = current_paragraph.split("\n\n")

        while len(paragraphs) > 1:
            current_paragraph = paragraphs[0].strip()
            if current_paragraph:
                await UniMessage(current_paragraph).send()
            paragraphs = paragraphs[1:]

        current_paragraph = paragraphs[-1].strip()

    if current_paragraph:
        await UniMessage(current_paragraph).finish()


@command_undo.handle()
async def handle_command_undo(event: Event):
    userid = event.get_user_id()
    response = await muice.undo(userid)
    await command_undo.finish(response)


@command_load.handle()
async def handle_command_load(config: Match[str] = AlconnaMatch("config_name")):
    config_name = config.result
    result = muice.change_model_config(config_name)
    await UniMessage(result).finish()


@command_whoami.handle()
async def handle_command_whoami(bot: Bot, event: Event):
    user_id = event.get_user_id()
    session = extract_session(bot, event)
    group_id = session.get_id(SessionIdType.GROUP)
    session_id = event.get_session_id()
    await UniMessage(f"用户 ID: {user_id}\n群组 ID: {group_id}\n当前会话信息: {session_id}").finish()


@command_start.handle()
async def handle_command_start():
    pass


@at_event.handle()
@nickname_event.handle()
async def handle_supported_adapters(
    message: UniMsg, event: Event, bot: Bot, state: T_State, matcher: Matcher, target: MsgTarget
):
    if not (merged_message := await session_manager.put_and_wait(event, message)):
        matcher.skip()
        return  # 防止类型检查器错误推断 merged_message 类型

    message_text = merged_message.extract_plain_text()
    message_images = merged_message.get(Image)

    userid = event.get_user_id()
    if not target.private:
        session = extract_session(bot, event)
        group_id = session.get_id(SessionIdType.GROUP)
    else:
        group_id = "-1"

    set_ctx(bot, event, state, matcher)  # 注册上下文信息以供插件、传统图片获取器使用

    images_set = set()

    for img in message_images if muice.model_config.multimodal else []:
        try:
            if not img.url:
                logger.warning("无法通过通用方式获取图片URL，回退至传统方式...")
                legacy_path = await legacy_get_images(img.origin, event)
                images_set.add(legacy_path)
            else:
                path = await save_image_as_file(img.url)
                images_set.add(path)
        except Exception as e:
            logger.error(f"处理图片失败: {e}")

    image_paths = list(images_set)

    logger.info(f"收到消息文本: {message_text} 图片体: {image_paths}")

    if not any((message_text, image_paths)):
        return

    # Stream
    if muice.model_config.stream:
        current_paragraph = ""

        async for chunk in muice.ask_stream(message_text, userid, group_id, image_paths=image_paths):
            current_paragraph += chunk
            paragraphs = current_paragraph.split("\n\n")

            while len(paragraphs) > 1:
                current_paragraph = paragraphs[0].strip()
                if current_paragraph:
                    await UniMessage(current_paragraph).send()
                paragraphs = paragraphs[1:]

            current_paragraph = paragraphs[-1].strip()

        if current_paragraph:
            await UniMessage(current_paragraph).finish()

        return

    # non-stream
    response = await muice.ask(message_text, userid, group_id, image_paths=image_paths)
    response = response.strip()

    logger.info(f"生成最终回复: {response}")

    paragraphs = response.split("\n\n")

    for index, paragraph in enumerate(paragraphs):
        if not paragraph.strip():
            continue  # 跳过空白文段
        if index == len(paragraphs) - 1:
            await UniMessage(paragraph).finish()
        await UniMessage(paragraph).send()
