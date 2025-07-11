from ollama import AsyncClient

from .._base import EmbeddingModel
from .._config import EmbeddingConfig
from .._schema import EmbeddingsBatchResult
from ..registry import register


@register("ollama")
class Ollama(EmbeddingModel):
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self._require("model")
        self.model = self.config.model
        self.host = self.config.api_host if self.config.api_host else "http://localhost:11434"
        self.client = AsyncClient(host=self.host)

    async def embed(self, texts: list[str]) -> EmbeddingsBatchResult:
        """
        查询文本嵌入
        """
        responses = await self.client.embed(model=self.model, input=texts)

        return EmbeddingsBatchResult([list(result) for result in responses.embeddings], usage=-1)
