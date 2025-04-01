from types import ModuleType
from typing import Any

from pydantic import BaseModel


class PluginMetadata(BaseModel):
    """MuiceBot 插件元数据"""

    name: str
    """插件名"""
    description: str
    """插件描述"""
    usage: str
    """插件用法"""
    homepage: str | None = None
    """(可选) 插件主页，通常为开源存储库地址"""
    config: type[BaseModel] | None = None
    """插件配置项类，如无需配置可不填写"""
    extra: dict[Any, Any] | None = None
    """不知道干嘛的 extra 信息，我至今都没搞懂，喜欢的可以填"""


class Plugin(BaseModel):
    """MuiceBot 插件对象"""

    name: str
    """插件名称"""
    module: ModuleType
    """插件模块对象"""
    package_name: str
    """模块包名"""

    def __hash__(self) -> int:
        return hash(self.package_name)

    def __eq__(self, other: Any) -> bool:
        return self.package_name == other.package_name if hasattr(other, "package_name") else False

    def __str__(self) -> str:
        return self.package_name

    class Config:
        arbitrary_types_allowed = True
