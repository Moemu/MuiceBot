import asyncio
from functools import partial

import dashscope

from .._base import EmbeddingModel
from .._config import EmbeddingConfig
from .._schema import EmbeddingsBatchResult
from ..registry import register


@register("dashscope")
class Dashscope(EmbeddingModel):
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self._require("api_key")
        self.api_key = self.config.api_key
        self.model = self.config.model

    async def embed(self, texts: list[str]) -> EmbeddingsBatchResult:
        """
        查询文本嵌入
        """
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,
            partial(
                dashscope.TextEmbedding.call,
                model=self.model,
                api_key=self.api_key,
                input=texts,
                dimension=1024,  # 指定向量维度（仅 text-embedding-v3及 text-embedding-v4支持该参数）
            ),
        )

        result: list[list[float]] = []
        for item in response.output.embeddings:
            result.append(item.embedding)

        return EmbeddingsBatchResult(result, response.usage.total_tokens)
