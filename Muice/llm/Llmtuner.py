from typing import AsyncGenerator, List, Literal, Optional, Tuple, Union, overload

import numpy as np
from llmtuner.chat import ChatModel
from nonebot import logger
from numpy.typing import NDArray
from PIL import Image

from ._types import BasicModel, ModelConfig
from .utils.auto_system_prompt import auto_system_prompt


class Llmtuner(BasicModel):
    """
    使用LLaMA-Factory方案加载, 适合通过其他微调方案微调的模型加载
    """

    def __init__(self, model_config: ModelConfig) -> None:
        super().__init__(model_config)
        self._require("model_path", "template")
        self.model_name_or_path = self.config.model_path
        self.adapter_name_or_path = self.config.adapter_path if self.config.adapter_path else None
        self.template = self.config.template
        self.system_prompt = self.config.system_prompt
        self.auto_system_prompt = self.config.auto_system_prompt
        self.max_tokens = self.config.max_tokens
        self.temperature = self.config.temperature
        self.top_p = self.config.top_p

    def load(self) -> bool:
        try:
            self.model = ChatModel(
                dict(
                    model_name_or_path=self.model_name_or_path,
                    adapter_name_or_path=self.adapter_name_or_path,
                    template=self.template,
                )
            )
            self.is_running = True
            return self.is_running
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False

    def _build_messages(
        self, prompt: str, history: List[Tuple[str, str]], images_path: Optional[List[str]] = None
    ) -> list:
        messages = []
        if self.auto_system_prompt:
            self.system_prompt = auto_system_prompt(prompt)
        if history:
            for chat in history:
                messages.append({"role": "user", "content": chat[0]})
                messages.append({"role": "assistant", "content": chat[1]})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def _ask_sync(self, messages: list, image: Optional[NDArray] = None) -> str:
        response = self.model.chat(
            messages,
            system=self.system_prompt,
            image=image,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
        )
        return response[0].response_text

    @overload
    async def ask(self, prompt: str, history: List[Tuple[str, str]], stream: Literal[False]) -> str: ...

    @overload
    async def ask(
        self, prompt: str, history: List[Tuple[str, str]], stream: Literal[True]
    ) -> AsyncGenerator[str, None]: ...

    async def ask(
        self, prompt: str, history: List[Tuple[str, str]], stream: Optional[bool] = False
    ) -> Union[str, AsyncGenerator[str, None]]:
        messages = self._build_messages(prompt, history)
        if stream:
            raise NotImplementedError(f"{self.config.loader} 不支持流式输出！")
        return await self._ask_sync(messages)

    # 多模态实现
    def _build_vision_image(self, image_path: str) -> NDArray:
        image = Image.open(image_path)
        ndarry_image = np.array(image)
        return ndarry_image

    @overload
    async def ask_vision(
        self, prompt, image_paths: List[str], history: List[Tuple[str, str]], stream: Literal[False]
    ) -> str: ...

    @overload
    async def ask_vision(
        self, prompt, image_paths: List[str], history: List[Tuple[str, str]], stream: Literal[True]
    ) -> AsyncGenerator[str, None]: ...

    async def ask_vision(
        self, prompt, image_paths: List[str], history: List[Tuple[str, str]], stream: bool = False
    ) -> Union[AsyncGenerator[str, None], str]:
        if stream:
            raise NotImplementedError(f"{self.config.loader} 不支持流式输出！")

        if len(image_paths) > 1:
            logger.warning("只能接受一张图片传入！")

        messages = self._build_messages(prompt, history)
        image = self._build_vision_image(image_paths[0])

        return await self._ask_sync(messages, image)
