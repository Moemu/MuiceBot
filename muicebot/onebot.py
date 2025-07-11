import os
import re
import time
from datetime import timedelta
from pathlib import Path
from typing import AsyncGenerator, Literal
from urllib.parse import urlparse

import nonebot_plugin_localstore as store
from arclet.alconna import Alconna, AllParam, Args
from nonebot import (
    get_adapters,
    get_driver,
    logger,
)
from nonebot.adapters import Bot, Event
from nonebot.adapters import Message as BotMessage
from nonebot.exception import FinishedException
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
    get_message_id,
    on_alconna,
    uniseg,
)
from nonebot_plugin_alconna.builtins.extensions import ReplyRecordExtension
from nonebot_plugin_alconna.uniseg import UniMsg
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_session import SessionIdType, extract_session

from .config import load_embedding_model_config, plugin_config
from .llm import ModelCompletions, ModelStreamCompletions
from .models import Message, Resource
from .muice import Muice
from .plugin import get_plugins, load_plugins, set_ctx
from .plugin.mcp import initialize_servers
from .scheduler import setup_scheduler
from .utils.SessionManager import SessionManager
from .utils.utils import download_file, get_file_via_adapter, get_version

COMMAND_PREFIXES = [".", "/"]
PLUGINS_PATH = Path("./plugins")
MCP_CONFIG_PATH = Path("./configs/mcp.json")
START_TIME = time.time()

scheduler = None
connect_time = 0.0
session_manager = SessionManager()

muice_nicknames = plugin_config.muice_nicknames
regex_patterns = [f"^{re.escape(nick)}\\s*" for nick in muice_nicknames]
combined_regex = "|".join(regex_patterns)

driver = get_driver()
adapters = get_adapters()


def startup_plugins():
    if PLUGINS_PATH.exists():
        logger.info("加载外部插件...")
        load_plugins("./plugins")

    if plugin_config.enable_builtin_plugins:
        logger.info("加载 MuiceBot 内嵌插件...")
        builtin_plugins_path = Path(__file__).parent / "builtin_plugins"
        muicebot_plugins_path = Path(__file__).resolve().parent.parent
        load_plugins(builtin_plugins_path, base_path=muicebot_plugins_path)


startup_plugins()


@driver.on_startup
async def load_bot():
    logger.info(f"MuiceBot 版本: {get_version()}")
    logger.info(f"MuiceBot 数据目录: {store.get_plugin_data_dir().resolve()}")
    logger.info("加载 MuiceBot 框架...")

    logger.info("初始化 Muice 实例...")
    muice = Muice.get_instance()

    logger.info(f"加载模型适配器: {muice.model_provider} ...")
    if not muice.load_model():
        logger.error("模型加载失败，请检查配置项是否正确")
        exit(1)
    load_embedding_model_config()
    logger.success(f"模型适配器加载成功: {muice.model_provider} ⭐")

    # if PLUGINS_PATH.exists():
    #     logger.info("加载外部插件...")
    #     load_plugins("./plugins")

    # if plugin_config.enable_builtin_plugins:
    #     logger.info("加载 MuiceBot 内嵌插件...")
    #     builtin_plugins_path = Path(__file__).parent / "builtin_plugins"
    #     muicebot_plugins_path = Path(__file__).resolve().parent.parent
    #     load_plugins(builtin_plugins_path, base_path=muicebot_plugins_path)

    if MCP_CONFIG_PATH.exists():
        logger.info("加载 MCP Server 配置")
        await initialize_servers()

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

command_profile = on_alconna(
    Alconna(
        COMMAND_PREFIXES,
        "profile",
        Args["profile", str, "_default"],
        meta=CommandMeta("切换消息存档", usage="profile Muika"),
    ),
    priority=10,
    block=True,
)

nickname_event = on_alconna(
    Alconna(re.compile(combined_regex), Args["text?", AllParam], separators=""),
    priority=99,
    block=True,
    extensions=[ReplyRecordExtension()],
)

at_event = on_alconna(
    Alconna(re.compile(".+"), Args["text?", AllParam], separators=""),
    priority=100,
    rule=to_me(),
    block=True,
    extensions=[ReplyRecordExtension()],
)


@driver.on_bot_connect
@command_schedule.handle()
async def on_bot_connect():
    global scheduler
    if not scheduler:
        scheduler = setup_scheduler(Muice.get_instance())


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
    muice = Muice.get_instance()

    model_loader = muice.model_provider
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
async def handle_command_status(session: async_scoped_session):
    now = time.time()
    uptime = timedelta(seconds=int(now - START_TIME))
    bot_uptime = timedelta(seconds=int(now - connect_time))
    muice = Muice.get_instance()

    model_status = "运行中" if muice.model and muice.model.is_running else "未启动"
    today_usage, total_usage = await muice.database.get_model_usage(session)

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
async def handle_command_reset(event: Event, session: async_scoped_session):
    muice = Muice.get_instance()
    userid = event.get_user_id()
    response = await muice.reset(userid, session)

    await session.commit()
    await command_reset.finish(response)


@command_refresh.handle()
async def handle_command_refresh(
    bot: Bot, event: Event, state: T_State, matcher: Matcher, session: async_scoped_session
):
    muice = Muice.get_instance()
    userid = event.get_user_id()

    set_ctx(bot, event, state, matcher)

    response = await muice.refresh(userid, session)

    await session.commit()
    await _send_message(response)


@command_undo.handle()
async def handle_command_undo(event: Event, session: async_scoped_session):
    muice = Muice.get_instance()
    userid = event.get_user_id()
    response = await muice.undo(userid, session)
    await session.commit()
    await command_undo.finish(response)


@command_load.handle()
async def handle_command_load(config: Match[str] = AlconnaMatch("config_name")):
    muice = Muice.get_instance()
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


@command_profile.handle()
async def handle_command_profile(
    event: Event, session: async_scoped_session, profile: Match[str] = AlconnaMatch("profile")
):
    from .database import UserORM

    userid = event.get_user_id()
    await UserORM.set_profile(session, userid, profile.result)
    await session.commit()
    await UniMessage("成功切换消息存档~").finish()


@command_start.handle()
async def handle_command_start():
    pass


def _get_media_filename(media: uniseg.segment.Media, type: Literal["audio", "image", "video", "file"]) -> str:
    """
    给多模态文件分配一个独一无二的文件名
    """
    _default_suffix = {"audio": "mp3", "image": "png", "video": "mp4", "file": ""}

    assert media.url  # 只能在 url 不为空时使用

    if media.name:
        file_suffix = media.name.split(".")[-1] if media.name.count(".") else _default_suffix[type]
    else:
        path = urlparse(media.url).path
        _, ext = os.path.splitext(path)
        file_suffix = ext.lstrip(".") if ext else _default_suffix[type]

    file_name = f"{time.time_ns()}.{file_suffix}"

    return file_name


async def _extract_multi_resource(
    message: UniMessage, type: Literal["audio", "image", "video", "file"], event: Event
) -> list[Resource]:
    """
    提取单个多模态文件
    """
    resources = []

    for resource in message:
        assert isinstance(resource, uniseg.segment.Media)  # 正常情况下应该都是 Media 的子类

        try:
            if resource.path is not None:
                path = str(resource.path)
            elif resource.url is not None:
                path = await download_file(resource.url, file_name=_get_media_filename(resource, type))
            elif resource.origin is not None:
                logger.warning("无法通过通用方式获取文件URL，回退至适配器自有方式...")
                path = await get_file_via_adapter(resource.origin, event)  # type:ignore
            else:
                continue

            if path:
                resources.append(Resource(type, path=path))
        except Exception as e:
            logger.error(f"处理文件失败: {e}")

    return resources


async def _extract_multi_resources(message: UniMsg, event: Event) -> list[Resource]:
    """
    提取多个多模态文件
    """
    resources = []

    message_audio = message.get(uniseg.Audio) + message.get(uniseg.Voice)
    message_images = message.get(uniseg.Image)
    message_file = message.get(uniseg.File)
    message_video = message.get(uniseg.Video)

    resources.extend(await _extract_multi_resource(message_audio, "audio", event))
    resources.extend(await _extract_multi_resource(message_file, "file", event))
    resources.extend(await _extract_multi_resource(message_images, "image", event))
    resources.extend(await _extract_multi_resource(message_video, "video", event))

    return resources


async def _send_multi_messages(resource: Resource):
    """
    发送多模态文件

    TODO: 我们有可能对发送对象添加文件名吗？
    """
    if resource.type == "audio":
        await UniMessage(uniseg.Voice(raw=resource.raw, path=resource.path)).send()
    elif resource.type == "image":
        await UniMessage(uniseg.Image(raw=resource.raw, path=resource.path)).send()
    elif resource.type == "video":
        await UniMessage(uniseg.Video(raw=resource.raw, path=resource.path)).send()
    else:
        await UniMessage(uniseg.File(raw=resource.raw, path=resource.path)).send()


async def _send_message(completions: ModelCompletions | AsyncGenerator[ModelStreamCompletions, None]):
    # non-stream
    if isinstance(completions, ModelCompletions):
        paragraphs = completions.text.split("\n\n")

        for index, paragraph in enumerate(paragraphs):
            if not paragraph.strip():
                continue  # 跳过空白文段
            if index == len(paragraphs) - 1:
                await UniMessage(paragraph).send()
                break
            await UniMessage(paragraph).send()

        if completions.resources:
            for resource in completions.resources:
                await _send_multi_messages(resource)

        raise FinishedException

    # stream
    current_paragraph = ""

    async for chunk in completions:
        logger.debug(chunk)
        current_paragraph += chunk.chunk
        paragraphs = current_paragraph.split("\n\n")

        while len(paragraphs) > 1:
            current_paragraph = paragraphs[0].strip()
            if current_paragraph:
                await UniMessage(current_paragraph).send()
            paragraphs = paragraphs[1:]

        current_paragraph = paragraphs[-1].strip()

        if chunk.resources:
            for resource in chunk.resources:
                await _send_multi_messages(resource)

    if current_paragraph:
        await UniMessage(current_paragraph).finish()


@at_event.handle()
@nickname_event.handle()
async def handle_supported_adapters(
    bot_message: UniMsg,
    event: Event,
    bot: Bot,
    state: T_State,
    matcher: Matcher,
    target: MsgTarget,
    ext: ReplyRecordExtension,
    db_session: async_scoped_session,
):
    if any((bot_message.startswith("."), bot_message.startswith("/"))):
        await UniMessage("未知的指令或权限不足").finish()

    # 先拿到引用消息并合并到 message (如果有)
    if message_reply := ext.get_reply(get_message_id(event, bot)):
        reply_message = message_reply.msg
        if isinstance(reply_message, BotMessage):
            bot_message += UniMessage("\n被引用的消息: ") + await UniMessage.generate(message=reply_message)
        else:
            bot_message += UniMessage(f"\n被引用的消息: {reply_message}")

    # 然后等待新消息插入
    if not (merged_message := await session_manager.put_and_wait(event, bot_message)):
        matcher.skip()
        return  # 防止类型检查器错误推断 merged_message 类型)

    message_text = merged_message.extract_plain_text()
    message_resource = await _extract_multi_resources(merged_message, event)

    userid = event.get_user_id()
    if not target.private:
        session = extract_session(bot, event)
        group_id = session.get_id(SessionIdType.GROUP)
    else:
        group_id = "-1"

    set_ctx(bot, event, state, matcher)  # 注册上下文信息以供插件、传统图片获取器使用

    logger.info(f"收到消息文本: {message_text} 多模态消息: {message_resource}")

    if not any((message_text, message_resource)):
        return

    message = Message(message=message_text, userid=userid, groupid=group_id, resources=message_resource)

    # Stream
    muice = Muice.get_instance()
    if muice.model_config.stream:
        stream_completions = muice.ask_stream(db_session, message)
        try:
            await _send_message(stream_completions)
        finally:
            await db_session.commit()
            return

    # non-stream
    completions = await muice.ask(db_session, message)

    logger.info(f"生成最终回复: {completions}")

    try:
        await _send_message(completions)
    finally:
        await db_session.commit()
