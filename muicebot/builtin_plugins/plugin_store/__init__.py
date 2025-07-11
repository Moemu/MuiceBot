from arclet.alconna import Alconna, Subcommand
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import Args, CommandMeta, Match, on_alconna

from muicebot.plugin import PluginMetadata

from .store import (
    get_installed_plugins_info,
    install_plugin,
    list_all_available_plugins,
    load_store_plugin,
    uninstall_plugin,
    update_plugin,
)

__plugin_meta__ = PluginMetadata(name="muicebot-plugin-store", description="Muicebot 插件商店操作", usage=".store help")

load_store_plugin()

COMMAND_PREFIXES = [".", "/"]

store_cmd = on_alconna(
    Alconna(
        COMMAND_PREFIXES,
        "store",
        Subcommand("help"),
        Subcommand("install", Args["name", str], help_text=".store install 插件名"),
        Subcommand("show"),
        Subcommand("update", Args["name", str], help_text=".store update 插件名"),
        Subcommand("uninstall", Args["name", str], help_text=".store uninstall 插件名"),
        meta=CommandMeta("Muicebot 插件商店指令"),
    ),
    priority=10,
    block=True,
    skip_for_unmatch=False,
    permission=SUPERUSER,
)


@store_cmd.assign("install")
async def install(name: Match[str]):
    if not name.available:
        await store_cmd.finish("必须传入一个插件名")
    result = await install_plugin(name.result)
    await store_cmd.finish(result)


@store_cmd.assign("list")
async def list():
    info = await list_all_available_plugins()
    await store_cmd.finish(info)


@store_cmd.assign("show")
async def show():
    info = await get_installed_plugins_info()
    await store_cmd.finish(info)


@store_cmd.assign("update")
async def update(name: Match[str]):
    if not name.available:
        await store_cmd.finish("必须传入一个插件名")
    result = await update_plugin(name.result)
    await store_cmd.finish(result)


@store_cmd.assign("uninstall")
async def uninstall(name: Match[str]):
    if not name.available:
        await store_cmd.finish("必须传入一个插件名")
    result = await uninstall_plugin(name.result)
    await store_cmd.finish(result)


@store_cmd.assign("help")
async def store_help():
    await store_cmd.finish(
        "install <插件名> 安装插件\n"
        "list 列出所有可用插件\n"
        "show 查看已安装的商店插件信息\n"
        "update <插件名> 更新插件\n"
        "uninstall <插件名> 卸载插件\n"
    )
