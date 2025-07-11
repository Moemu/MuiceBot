import base64
import struct

from azure.ai.inference.aio import EmbeddingsClient
from azure.core.credentials import AzureKeyCredential

from .._base import EmbeddingModel
from .._config import EmbeddingConfig
from .._schema import EmbeddingsBatchResult
from ..registry import register


@register("azure")
class Azure(EmbeddingModel):
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self.token = self.config.api_key
        self.endpoint = self.config.api_host if self.config.api_host else "https://models.inference.ai.azure.com"
        self.model = self.config.model

    async def embed(self, texts: list[str]) -> EmbeddingsBatchResult:
        """
        查询文本嵌入
        """
        client = EmbeddingsClient(endpoint=self.endpoint, credential=AzureKeyCredential(self.token))

        response = await client.embed(input=texts, model=self.model)
        results: list[list[float]] = []

        for item in response.data:
            if isinstance(item.embedding, str):
                binary = base64.b64decode(item.embedding)
                embedding = list(struct.unpack(f"{len(binary) // 4}f", binary))
            else:
                embedding = item.embedding

            results.append(embedding)

        return EmbeddingsBatchResult(results, usage=response.usage.total_tokens)
