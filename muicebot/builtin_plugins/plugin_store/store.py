import asyncio
import shutil
from pathlib import Path
from typing import Optional

import aiohttp
from nonebot import logger

from muicebot.plugin import load_plugin

from .config import config
from .models import PluginInfo
from .register import load_json_record, register_plugin, unregister_plugin

PLUGIN_DIR = Path("plugins/store")
PLUGIN_DIR.mkdir(parents=True, exist_ok=True)


async def get_index() -> Optional[dict[str, PluginInfo]]:
    """
    获取插件索引
    """
    logger.info("获取插件索引文件...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(config.store_index) as response:
                response.raise_for_status()
                return await response.json(content_type=None)
    except aiohttp.ClientError as e:
        logger.error(f"获取插件索引失败: {e}")
    except Exception as e:
        logger.exception(f"解析插件索引时发生意外错误: {e}")
    return {}


async def get_plugin_commit(plugin: str) -> str:
    """
    获取插件 commit hash
    """
    plugin_path = PLUGIN_DIR / plugin

    process = await asyncio.create_subprocess_exec(
        "git",
        "log",
        "--pretty=format:%h",
        "-1",
        cwd=plugin_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    return stdout.decode().strip()


def load_store_plugin():
    """
    加载商店插件
    """
    logger.info("加载商店插件...")
    plugins = load_json_record()

    for plugin, info in plugins.items():
        if not Path(PLUGIN_DIR / plugin).exists():
            continue

        module_path = PLUGIN_DIR / plugin / info["module"]
        load_plugin(module_path)


async def install_dependencies(path: Path) -> bool:
    """
    安装插件依赖

    :return: 依赖安装状态
    """
    logger.info("安装插件依赖...")

    if (path / "pyproject.toml").exists():
        cmd = ["python", "-m", "pip", "install", "."]
    elif (path / "requirements.txt").exists():
        cmd = ["python", "-m", "pip", "install", "-r", "requirements.txt"]
    else:
        return True

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode == 0:
        return True
    else:
        logger.error("插件依赖安装失败!")
        logger.error(stderr)
        return False


async def get_installed_plugins_info() -> str:
    """
    获得已安装插件信息
    """
    plugins = load_json_record()
    plugins_info = []
    for plugin, info in plugins.items():
        plugins_info.append(f"{plugin}: {info['name']} {info['commit']}")
    return "\n".join(plugins_info) or "本地还未安装商店插件~"


async def install_plugin(plugin: str) -> str:
    """
    通过 git clone 安装指定插件
    """
    if not (index := await get_index()):
        return "❌ 无法获取插件索引文件，请检查控制台日志"

    if plugin not in index:
        return f"❌ 插件 {plugin} 不存在于索引中！请检查插件名称是否正确"

    repo_url = index[plugin]["repo"]
    module = index[plugin]["module"]
    plugin_path = PLUGIN_DIR / plugin

    if plugin_path.exists():
        return f"⚠️ 插件 {plugin} 已存在，无需安装。"

    logger.info(f"获取插件: {repo_url}")
    try:
        process = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            repo_url,
            str(plugin_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return f"❌ 安装失败：{stderr.decode().strip()}"

        if not await install_dependencies(plugin_path):
            return "❌ 插件依赖安装失败！请检查控制台输出"

    except FileNotFoundError:
        return "❌ 请确保已安装 Git 并配置到 PATH。"

    load_plugin(plugin_path / module)

    commit = await get_plugin_commit(plugin)

    register_plugin(plugin, commit, module)

    return f"✅ 插件 {plugin} 安装成功！"


async def update_plugin(plugin: str) -> str:
    """
    更新指定插件
    """
    plugin_path = PLUGIN_DIR / plugin

    if not plugin_path.exists():
        return f"❌ 插件 {plugin} 不存在！"

    logger.info(f"更新插件: {plugin}")
    try:
        process = await asyncio.create_subprocess_exec(
            "git",
            "pull",
            cwd=plugin_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return f"❌ 插件更新失败：{stderr.decode().strip()}"

    except FileNotFoundError:
        return "❌ 请确保已安装 Git 并配置到 PATH。"

    await install_dependencies(plugin_path)

    info = load_json_record()[plugin]
    commit = await get_plugin_commit(plugin)
    register_plugin(plugin, commit, info["module"])

    return f"✅ 插件 {plugin} 更新成功！重启后生效"


async def uninstall_plugin(plugin: str) -> str:
    """
    卸载指定插件
    """
    plugin_path = PLUGIN_DIR / plugin

    if not plugin_path.exists():
        return f"❌ 插件 {plugin} 不存在！"

    logger.info(f"卸载插件: {plugin}")

    unregister_plugin(plugin)

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, shutil.rmtree, plugin_path)
    except PermissionError:
        return f"⚠️ 插件 {plugin} 虽然已从加载列表中移除，但其文件移除失败，请尝试手动删除此插件"

    return f"✅ 插件 {plugin} 移除成功！重启后生效"


async def list_all_available_plugins() -> str:
    """
    列出所有可用插件
    """
    if not (index := await get_index()):
        return "❌ 无法获取插件索引文件，请检查控制台日志"

    available_plugins = []
    for plugin, info in index.items():
        available_plugins.append(f"{plugin}: {info['description']}")

    if not available_plugins:
        return "❌ 当前没有可用的插件"

    return "\n".join(available_plugins)
