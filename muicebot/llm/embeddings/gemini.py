from google import genai

from .._base import EmbeddingModel
from .._config import EmbeddingConfig
from .._schema import EmbeddingsBatchResult
from ..registry import register


@register("gemini")
class Gemini(EmbeddingModel):
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self._require("api_key", "model")
        self.api_key = self.config.api_key
        self.model = self.config.model
        self.client = genai.Client(api_key=self.api_key)

    async def embed(self, texts: list[str]) -> EmbeddingsBatchResult:
        """
        查询文本嵌入
        """
        result = await self.client.aio.models.embed_content(model=self.model, contents=texts)  # type:ignore

        if not result.embeddings:
            raise RuntimeError("Gemini 嵌入查询无返回！")

        return EmbeddingsBatchResult(
            [embedding.values for embedding in result.embeddings if embedding.values is not None],
            usage=-1,  # Unsupported.
        )
