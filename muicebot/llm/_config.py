from importlib.util import find_spec
from typing import Any, List, Literal, Optional
from warnings import warn

from pydantic import BaseModel, field_validator, model_validator


class ModelConfig(BaseModel):
    provider: str
    """所使用模型提供者的名称，位于 llm/providers 下"""
    loader: Optional[str] = None
    """[弃用] 所使用加载器的名称，位于 llm 文件夹下，loader 开头必须大写"""
    default: bool = False
    """是否默认启用"""

    template: Optional[str] = "Muice"
    """使用的人设模板名称"""
    template_mode: Literal["system", "user"] = "system"
    """模板嵌入模式: `system` 为嵌入到系统提示; `user` 为嵌入到用户提示中"""

    max_tokens: int = 4096
    """最大回复 Tokens """
    temperature: float = 0.75
    """模型的温度系数"""
    top_p: float = 0.95
    """模型的 top_p 系数"""
    top_k: float = 3
    """模型的 top_k 系数"""
    frequency_penalty: Optional[float] = None
    """模型的频率惩罚"""
    presence_penalty: Optional[float] = None
    """模型的存在惩罚"""
    repetition_penalty: Optional[float] = None
    """模型的重复惩罚"""
    stream: bool = False
    """是否使用流式输出"""
    online_search: bool = False
    """是否启用联网搜索（原生实现）"""
    function_call: bool = False
    """是否启用工具调用"""
    content_security: bool = False
    """是否启用内容安全"""

    model_path: str = ""
    """本地模型路径"""
    adapter_path: str = ""
    """基于 model_path 的微调模型或适配器路径"""

    model_name: str = ""
    """所要使用模型的名称"""
    api_key: str = ""
    """在线服务的 API KEY"""
    api_secret: str = ""
    """在线服务的 api secret """
    api_host: str = ""
    """自定义 API 地址"""

    extra_body: Optional[dict] = None
    """OpenAI 的 extra_body"""
    enable_thinking: Optional[bool] = None
    """Dashscope 的 enable_thinking"""
    thinking_budget: Optional[int] = None
    """Dashscope 的 thinking_budget"""

    multimodal: bool = False
    """是否为（或启用）多模态模型"""
    modalities: List[Literal["text", "audio", "image"]] = ["text"]
    """生成模态"""
    audio: Optional[Any] = None
    """多模态音频参数"""

    @field_validator("provider")
    @classmethod
    def check_model_loader(cls, provider: str) -> str:
        if not provider:
            raise ValueError("provider is required")

        provider = provider.lower()

        # Check if the specified loader exists
        module_path = f"muicebot.llm.providers.{provider}"

        # 使用 find_spec 仅检测模块是否存在，不实际导入
        if find_spec(module_path) is None:
            raise ValueError(f"指定的模型加载器 '{provider}' 不存在于 llm 目录中")

        return provider

    @model_validator(mode="before")
    @classmethod
    def migrate_old_field(cls, values: dict):
        if "provider" not in values and "loader" in values:
            values["provider"] = values["loader"]
            warn("配置文件中的 'loader' 字段已弃用，请使用 'provider' 字段。", DeprecationWarning)
        return values


class EmbeddingConfig(BaseModel):
    provider: str
    """所使用模型提供者的名称，位于 llm/embedding 下"""
    default: bool = False
    """是否默认启用"""

    model: str = "text-embedding-v4"
    """嵌入模型名称"""

    api_key: str = ""
    """在线服务的 API KEY"""
    api_secret: str = ""
    """在线服务的 api secret """
    api_host: str = ""
    """自定义 API 地址"""

    # binding_model_config: Optional[str] = None
    # """
    # 绑定的模型配置。如果切换模型，会查找该模型所绑定的嵌入配置。如果不指定绑定配置，则不切换。
    # 对于绝大多数任务，使用一个通用的嵌入配置即可
    # """
    # 未知该配置项的实用性，先注释掉

    def __hash__(self) -> int:
        return hash(self.provider + self.model + self.api_host)

    def __eq__(self, other) -> bool:
        if not isinstance(other, EmbeddingConfig):
            return NotImplemented

        return self.provider == other.provider and self.model == other.model and self.api_host == other.api_host

    @field_validator("provider")
    @classmethod
    def check_model_loader(cls, provider: str) -> str:
        if not provider:
            raise ValueError("provider is required")

        provider = provider.lower()

        # Check if the specified loader exists
        module_path = f"muicebot.llm.embeddings.{provider}"

        # 使用 find_spec 仅检测模块是否存在，不实际导入
        if find_spec(module_path) is None:
            raise ValueError(f"指定的模型加载器 '{provider}' 不存在于 llm 目录中")

        return provider
