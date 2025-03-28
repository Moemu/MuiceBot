# plugin_manager.py
import importlib
import os
from pathlib import Path
from typing import Dict, List, Optional

from nonebot import logger

from .models import Plugin
from .utils import path_to_module_name

_plugins: List[Dict[str, Plugin]] = []
"""插件列表"""


def load_plugin(plugin_path: Path | str) -> Optional[Plugin]:
    """
    加载单个插件
    """
    try:
        logger.debug(f"加载插件: {plugin_path} ...")
        if isinstance(plugin_path, Path):
            plugin_path = path_to_module_name(plugin_path)
        module = importlib.import_module(plugin_path)
        plugin = Plugin(name=module.__name__.split(".")[-1], module=module, package_name=plugin_path)

        if plugin.package_name in _plugins:
            ValueError(f"插件 {plugin_path} 包名出现冲突！")

        _plugins.append({plugin.package_name: plugin})
        logger.success(f"成功加载: {plugin_path}")

        return plugin

    except Exception as e:
        logger.error(f"加载插件 {plugin_path} 失败: {e}")
        return None


def load_plugins(*plugins_dirs: str) -> set[Plugin]:
    """
    加载传入插件目录中的所有插件
    """

    plugins = set()

    for plugin_dir in plugins_dirs:
        plugin_dir_path = Path(plugin_dir)

        for plugin in os.listdir(plugin_dir_path):
            plugin_path = Path(os.path.join(plugin_dir_path, plugin))
            module_name = None

            if plugin_path.is_file() and plugin_path.suffix == ".py":
                module_name = path_to_module_name(plugin_path.parent / plugin_path.stem)
            elif plugin_path.is_dir() and (plugin_path / Path("__init__.py")).exists():
                module_name = path_to_module_name(plugin_path)
            if module_name and (loaded_plugin := load_plugin(module_name)):
                plugins.add(loaded_plugin)

    return plugins


def get_plugins() -> List[Dict[str, Plugin]]:
    """
    获取插件列表
    """
    return _plugins
