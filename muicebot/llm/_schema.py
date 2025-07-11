from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Literal, Optional, Type

from pydantic import BaseModel

from ..models import Message, Resource

if TYPE_CHECKING:
    from numpy import ndarray


@dataclass
class ModelRequest:
    """
    模型调用请求
    """

    prompt: str
    history: List[Message] = field(default_factory=list)
    resources: List[Resource] = field(default_factory=list)
    tools: Optional[List[dict]] = field(default_factory=list)
    system: Optional[str] = None
    format: Literal["string", "json"] = "string"
    json_schema: Optional[Type[BaseModel]] = None


@dataclass
class ModelCompletions:
    """
    模型输出
    """

    text: str = ""
    """输出文本内容"""
    usage: int = -1
    """总调用用量"""
    resources: List[Resource] = field(default_factory=list)
    """模型输出多模态资源列表"""
    succeed: bool = True
    """调用成功（如不成功会在 `text` 中输出错误信息）"""


@dataclass
class ModelStreamCompletions:
    """
    模型流式输出
    """

    chunk: str = ""
    """输出文本块"""
    usage: int = -1
    """总调用用量（累增，一般取最后一个块的用量）"""
    resources: Optional[List[Resource]] = field(default_factory=list)
    """模型输出多模态资源列表"""
    succeed: bool = True
    """调用成功（如不成功会在 `chunk` 中输出错误信息）"""


@dataclass
class EmbeddingsBatchResult:
    """
    嵌入输出
    """

    embeddings: List[List[float]]
    usage: int = -1
    succeed: bool = True

    @property
    def array(self) -> List["ndarray"]:
        from numpy import array

        return [array(embedding) for embedding in self.embeddings]
