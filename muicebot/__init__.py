from nonebot import require

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_apscheduler")

from nonebot.plugin import PluginMetadata, inherit_supported_adapters  # noqa: E402

from .config import Config  # noqa: E402
from .onebot import *  # noqa: E402, F403, F401
from .utils.utils import init_logger  # noqa: E402

init_logger()

__plugin_meta__ = PluginMetadata(
    name="MuiceBot",
    description="Muice-Chatbot 的 Nonebot2 实现，支持市面上大多数的模型",
    usage="@at / {config.MUICE_NICKNAMES} <message>: 与大语言模型交互；关于指令类可输入 .help 查询",
    type="application",
    config=Config,
    homepage="https://bot.snowy.moe/",
    extra={},
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)
