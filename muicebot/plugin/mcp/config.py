import json
import shutil
from pathlib import Path
from typing import Any, Literal

from nonebot import logger
from pydantic import BaseModel, Field, ValidationError, model_validator

CONFIG_PATH = Path("./configs/mcp.json")


class McpServer(BaseModel):
    command: str | None = Field(default=None)
    """执行指令"""
    args: list[str] = Field(default_factory=list)
    """命令参数"""
    env: dict[str, Any] = Field(default_factory=dict)
    """环境配置"""
    headers: dict[str, Any] = Field(default_factory=dict)
    """HTTP请求头 (用于sse和streamable_http传输方式)"""
    type: Literal["stdio", "sse", "streamable_http"] = Field(default="stdio")
    """传输方式: stdio, sse, streamable_http"""
    url: str | None = Field(default=None)
    """服务器URL (用于sse和streamable_http传输方式)"""

    @model_validator(mode="before")
    def validate_config(cls, values: dict[str, Any]) -> dict[str, Any]:
        srv_type = values.get("type", "stdio")
        command = values.get("command")
        url = values.get("url")

        if srv_type == "stdio":
            if not command:
                raise ValueError("当 type 为 'stdio' 时，command 字段必须存在")
            # 检查 command 是否为可执行的命令
            if not shutil.which(command):
                raise ValueError(f"命令 '{command}' 不存在或不可执行。")
        elif srv_type in ["sse", "streamable_http"] and not url:
            raise ValueError(f"当 type 为 '{srv_type}' 时，url 字段必须存在")

        return values


McpConfig = dict[str, McpServer]


def get_mcp_server_config() -> McpConfig:
    """
    从 MCP 配置文件 `config/mcp.json` 中获取 MCP Server 配置
    """
    if not CONFIG_PATH.exists():
        return {}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            configs = json.load(f) or {}
    except json.JSONDecodeError as e:
        # 如果 JSON 解码失败，记录错误并返回空配置
        logger.error(f"读取MCP配置时发生JSON解码错误: {e}")
        return {}
    except (IOError, OSError) as e:
        # 处理文件读取相关的异常
        logger.error(f"读取MCP配置文件时发生IO错误: {e}")
        return {}

    mcp_config: McpConfig = dict()

    if not isinstance(configs, dict):
        logger.warning("MCP配置文件顶层必须是一个JSON对象，而不是列表或其他类型。")
        return mcp_config

    mcp_servers = configs.get("mcpServers")
    if isinstance(mcp_servers, dict):
        for name, srv_config in mcp_servers.items():
            try:
                mcp_config[name] = McpServer(**srv_config)
            except (ValidationError, TypeError) as e:
                logger.warning(f"无效的MCP服务器配置 '{name}': {e}")
                continue

    return mcp_config
