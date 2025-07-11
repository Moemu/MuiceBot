from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator, Literal, Optional, Union, overload

import numpy as np
from nonebot import logger
from nonebot_plugin_localstore import get_plugin_data_dir
from numpy import ndarray

from ._config import EmbeddingConfig, ModelConfig
from ._schema import (
    EmbeddingsBatchResult,
    ModelCompletions,
    ModelRequest,
    ModelStreamCompletions,
)


class BaseLLM(ABC):
    """
    模型基类，所有模型加载器都必须继承于该类

    推荐使用该基类中定义的方法构建模型加载器类，但无论如何都必须实现 `ask` 方法
    """

    def __init__(self, model_config: ModelConfig) -> None:
        """
        统一在此处声明变量
        """
        self.config = model_config
        """模型配置"""
        self.is_running = False
        """模型状态"""

    def __init_subclass__(cls, **kwargs):
        """
        对实现类中的 `ask` 函数包装 `record_plugin_usage` 装饰器
        """
        from ._wrapper import record_plugin_usage

        super().__init_subclass__(**kwargs)

        # 1. Get the original 'ask' method from the new subclass
        original_ask = cls.ask

        # 2. Wrap it with the decorator
        decorated_ask = record_plugin_usage(original_ask)

        # 3. Replace the original method on the subclass with the decorated version
        setattr(cls, "ask", decorated_ask)

    def _require(self, *require_fields: str):
        """
        通用校验方法：检查指定的配置项是否存在，不存在则抛出错误

        :param require_fields: 需要检查的字段名称（字符串）
        """
        missing_fields = [field for field in require_fields if not getattr(self.config, field, None)]
        if missing_fields:
            raise ValueError(f"对于 {self.config.provider} 以下配置是必需的: {', '.join(missing_fields)}")

    def _build_messages(self, request: "ModelRequest") -> list:
        """
        构建对话上下文历史的函数
        """
        raise NotImplementedError

    def load(self) -> bool:
        """
        加载模型（通常是耗时操作，在线模型如无需校验可直接返回 true）

        :return: 是否加载成功
        """
        self.is_running = True
        return True

    async def _ask_sync(
        self, messages: list, tools: Any, response_format: Any, total_tokens: int = 0
    ) -> "ModelCompletions":
        """
        同步模型调用
        """
        raise NotImplementedError

    def _ask_stream(
        self, messages: list, tools: Any, response_format: Any, total_tokens: int = 0
    ) -> AsyncGenerator["ModelStreamCompletions", None]:
        """
        流式输出
        """
        raise NotImplementedError

    @overload
    async def ask(self, request: "ModelRequest", *, stream: Literal[False] = False) -> "ModelCompletions": ...

    @overload
    async def ask(
        self, request: "ModelRequest", *, stream: Literal[True] = True
    ) -> AsyncGenerator["ModelStreamCompletions", None]: ...

    @abstractmethod
    async def ask(
        self, request: "ModelRequest", *, stream: bool = False
    ) -> Union["ModelCompletions", AsyncGenerator["ModelStreamCompletions", None]]:
        """
        模型交互询问

        :param request: 模型调用请求体
        :param stream: 是否开启流式对话

        :return: 模型输出体
        """
        pass


class EmbeddingModel(ABC):
    """
    嵌入模型基类，所有模型加载器都必须继承于该类

    推荐使用该基类中定义的方法构建模型加载器类，但无论如何都必须实现 `embed` 方法
    """

    def __init__(self, config: EmbeddingConfig):
        from ..config import plugin_config

        self.config = config
        self.enable_embedding_cache = plugin_config.enable_embedding_cache

        if self.enable_embedding_cache:
            self.cache_dir = get_plugin_data_dir() / "embedding"
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.cache_dir = None

    def __init_subclass__(cls, **kwargs):
        """
        对实现类中的 `embed` 函数包装 `record_plugin_embedding_usage` 装饰器
        """
        from ._wrapper import cache, record_plugin_embedding_usage

        super().__init_subclass__(**kwargs)

        original_embed = cls.embed
        decorated_embed = cache(record_plugin_embedding_usage(original_embed))
        setattr(cls, "embed", decorated_embed)

    def _require(self, *require_fields: str):
        """
        通用校验方法：检查指定的配置项是否存在，不存在则抛出错误

        :param require_fields: 需要检查的字段名称（字符串）
        """
        missing_fields = [field for field in require_fields if not getattr(self.config, field, None)]
        if missing_fields:
            raise ValueError(f"对于 {self.config.provider} 嵌入模型，以下配置是必需的: {', '.join(missing_fields)}")

    def _get_embedding_cache_path(self, text: str) -> Optional[Path]:
        """
        获取嵌入缓存文件路径

        :param text: 查询文本
        """
        if not self.cache_dir:
            return None

        # 根据文本和模型名称生成缓存键
        content = f"{self.config.model}:{text}"
        cache_key = hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()

        return self.cache_dir / cache_key

    @lru_cache(maxsize=256)
    def _load_embedding_from_cache(self, text: str) -> Optional[ndarray]:
        """
        从缓存文件中加载嵌入向量

        :param text: 查询文本
        """
        if not self.enable_embedding_cache:
            return None

        try:
            cache_path = self._get_embedding_cache_path(text)
            if not cache_path:
                return None

            meta_path = cache_path.with_suffix(".json")
            npy_path = cache_path.with_suffix(".npy")

            if not (meta_path.exists() and npy_path.exists()):
                return None

            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            if (
                isinstance(meta, dict)
                and meta.get("provider", None) == self.__class__.__name__
                and meta.get("api_host", None) == self.config.api_host
                and meta.get("model", None) == self.config.model
                and meta.get("text_hash", "") == hashlib.sha256(text.encode("utf-8")).hexdigest()
            ):
                embedding = np.load(npy_path)
                logger.debug(f"从缓存加载嵌入向量: {text[:50]}...")
                return embedding
            return None

        except Exception as e:
            logger.warning(f"加载缓存失败: {e}")
            return None

    def _save_to_cache(self, text: str, embedding: list[float]) -> None:
        """
        将嵌入向量保存到缓存文件
        """
        if not self.enable_embedding_cache or not self.cache_dir:
            return

        try:
            cache_path = self._get_embedding_cache_path(text)
            if not cache_path:
                return

            meta_path = cache_path.with_suffix(".json")
            npy_path = cache_path.with_suffix(".npy")

            meta_data = {
                "provider": self.__class__.__name__,
                "api_host": self.config.api_host,
                "model": self.config.model,
                "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f)
            np.save(npy_path, np.array(embedding), allow_pickle=False)

            logger.debug(f"嵌入向量已缓存: {text[:50]}...")
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")

    @abstractmethod
    async def embed(self, texts: list[str]) -> "EmbeddingsBatchResult":
        """
        查询文本嵌入
        """
        raise NotImplementedError
