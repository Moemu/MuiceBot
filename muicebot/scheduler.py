import random

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v12 import Message

from .config import get_schedule_configs
from .muice import Muice


async def send_message(bot: Bot, message: str, **kwargs):
    """
    定时任务：发送信息

    :param bot: 适配器提供的 Bot 类
    **kwargs 中与 bot 交互所需要的参数可参见 https://onebot.adapters.nonebot.dev/docs/api/v12/bot#Bot-send
    """
    probability = kwargs.get("random", 1)
    if not (random.random() < probability):
        return

    logger.info(f"定时任务: send_message: {message}")

    kwargs.update({"message": Message(message)})
    await bot.call_api("send_message", **kwargs)


async def model_ask(muice_app: Muice, bot: Bot, prompt: str, **kwargs):
    """
    定时任务：向模型发送消息

    :param muice_app: 沐雪核心类，用于与大语言模型交互
    :param bot: 适配器提供的 Bot 类
    :param prompt: 模型提示词

    **kwargs 中与 bot 交互所需要的参数可参见 https://onebot.adapters.nonebot.dev/docs/api/v12/bot#Bot-send
    """
    probability = kwargs.get("random", 1)
    if not (random.random() < probability):
        return

    logger.info(f"定时任务: model_ask: {prompt}")
    self_info = await bot.call_api("get_self_info")
    self_id = self_info["user_id"]

    if muice_app.model and muice_app.model.is_running:
        message = await muice_app.ask(
            prompt,
            self_id,
            enable_history=False,
        )

    kwargs.update({"message": Message(message)})

    await bot.call_api("send_message", **kwargs)


def setup_scheduler(muice: Muice, bot: Bot) -> AsyncIOScheduler:
    """
    设置任务调度器

    :param muice: 沐雪核心类，用于与大语言模型交互
    """
    jobs = get_schedule_configs()
    scheduler = AsyncIOScheduler()

    if not jobs:
        jobs = []

    for job in jobs:
        job_id = job.id
        job_type = "send_message" if job.say else "model_ask"
        trigger_type = job.trigger
        trigger_args = job.args
        bot_args = job.target

        # 解析触发器
        if trigger_type == "cron":
            trigger = CronTrigger(**trigger_args)

        elif trigger_type == "interval":
            trigger = IntervalTrigger(**trigger_args)

        else:
            logger.error(f"未知的触发器类型: {trigger_type}")
            continue

        # 添加任务
        if job_type == "send_message":
            scheduler.add_job(
                send_message,
                trigger,
                id=job_id,
                replace_existing=True,
                args=[bot, job.say],
                kwargs=bot_args,
            )
        else:
            scheduler.add_job(
                model_ask,
                trigger,
                id=job_id,
                replace_existing=True,
                args=[muice, bot, job.ask],
                kwargs=bot_args,
            )

        logger.success(f"已注册定时任务: {job_id}")

    scheduler.start()
    return scheduler
