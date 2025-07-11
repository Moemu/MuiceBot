import openai

from .._base import EmbeddingModel
from .._config import EmbeddingConfig
from .._schema import EmbeddingsBatchResult
from ..registry import register


@register("openai")
class OpenAI(EmbeddingModel):
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self._require("api_key")
        self.api_key = self.config.api_key
        self.api_base = self.config.api_host or "https://api.openai.com/v1"
        self.model = self.config.model

        self.client = openai.AsyncOpenAI(api_key=self.api_key, base_url=self.api_base, timeout=30)

    async def embed(self, texts: list[str]) -> EmbeddingsBatchResult:
        """
        查询文本嵌入
        """
        completion = await self.client.embeddings.create(model=self.model, input=texts, encoding_format="float")

        return EmbeddingsBatchResult([item.embedding for item in completion.data], usage=completion.usage.total_tokens)
