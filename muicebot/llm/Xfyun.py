import asyncio
import base64
import hashlib
import hmac
import json
import ssl
import threading
import time
from datetime import datetime
from functools import partial
from time import mktime
from typing import (
    AsyncGenerator,
    Generator,
    List,
    Literal,
    Optional,
    Union,
    overload,
)
from urllib.parse import urlencode, urlparse
from wsgiref.handlers import format_date_time

import websocket
from nonebot import logger

from ._types import BasicModel, Message, ModelConfig
from .utils.auto_system_prompt import auto_system_prompt


class Xfyun(BasicModel):
    """
    星火大模型
    """

    def __init__(self, model_config: ModelConfig) -> None:
        super().__init__(model_config)
        self._require("app_id", "api_key", "api_secret", "service_id", "resource_id")
        self.app_id = self.config.app_id
        self.api_key = self.config.api_key
        self.api_secret = self.config.api_secret
        self.service_id = self.config.service_id
        self.resource_id = self.config.resource_id
        self.system_prompt = self.config.system_prompt
        self.auto_system_prompt = self.config.auto_system_prompt
        self.temperature = self.config.temperature
        self.top_k = self.config.top_k
        self.max_tokens = self.config.max_tokens
        self.stream = self.config.stream

        self.url = self.config.api_host if self.config.api_host else "wss://maas-api.cn-huabei-1.xf-yun.com/v1.1/chat"
        self.host = urlparse(self.url).netloc
        self.path = urlparse(self.url).path

        self.stream_queue: asyncio.Queue = asyncio.Queue()
        self.response = ""
        self.is_insert_think_label = False

    def _add_think_tag(self, text_body: dict) -> str:
        """
        添加思考过程标签
        """
        answer_content = text_body["content"]
        reasoning_content = text_body.get("reasoning_content", "")

        if reasoning_content and answer_content and not self.stream:
            return f"<think>{reasoning_content}</think>{answer_content}"

        elif reasoning_content != "" and answer_content == "":
            if not self.is_insert_think_label:
                self.is_insert_think_label = True
                reasoning_content = "<think>" + reasoning_content
            return reasoning_content

        elif answer_content != "":
            if self.is_insert_think_label:
                self.is_insert_think_label = False
                answer_content = "</think>" + answer_content
            return answer_content

        return ""

    def _create_url(self) -> str:
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = "host: " + self.host + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + self.path + " HTTP/1.1"

        signature_sha = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        signature_sha_base64 = base64.b64encode(signature_sha).decode(encoding="utf-8")

        authorization_origin = (
            f'api_key="{self.api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature_sha_base64}"'
        )

        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode(encoding="utf-8")

        v = {"authorization": authorization, "date": date, "host": self.host}
        url = self.url + "?" + urlencode(v)
        return url

    def __on_message(self, ws, message):
        response = json.loads(message)
        # logger.debug(f"Spark返回数据: {response}")

        if response["header"]["code"] != 0:  # 不合规时该值为10013
            error_message = f"调用Spark在线模型时发生错误: {response['header']['message']}"
            logger.warning(error_message)
            self.response = error_message
            if self.stream:
                self.stream_queue.put_nowait(error_message)
                self.stream_queue.put_nowait(None)  # 表示流结束
            ws.close()
            return

        text_body = response["payload"]["choices"]["text"][0]

        if response["header"]["status"] in [0, 1, 2]:
            content = self._add_think_tag(text_body)
            self.response += content
            if self.stream:
                self.stream_queue.put_nowait(content)

        if response["header"]["status"] == 2:
            if self.stream:
                self.stream_queue.put_nowait(None)  # 表示流结束
            ws.close()

    def __on_error(self, ws, error):
        logger.error(f"调用Spark在线模型时发生错误: {error}")
        ws.close()

    def __on_close(self, ws, close_status_code, close_msg):
        pass

    def __on_open(self, ws):
        request_data = {
            "header": {"app_id": self.app_id, "patch_id": [self.resource_id]},
            "parameter": {
                "chat": {
                    "domain": self.service_id,
                    "temperature": self.temperature,
                    "top_k": self.top_k,
                    "max_tokens": self.max_tokens,
                }
            },
            "payload": {"message": {"text": self.messages}},
        }
        ws.send(json.dumps(request_data))

    def __generate_system_prompt(self, user_text: str) -> str:
        if self.auto_system_prompt:
            return "system\n\n" + auto_system_prompt(user_text) + "user\n\n"
        return "system\n\n" + self.system_prompt + "user\n\n"

    def _build_messages(self, prompt: str, history: List[Message], images_path: Optional[List[str]] = None) -> list:
        messages = []

        if len(history) > 0:
            messages.append(
                {
                    "role": "user",
                    "content": self.__generate_system_prompt(history[0].message) + history[0].message,
                }
            )

        for item in history:
            messages.append({"role": "user", "content": item.message})
            messages.append({"role": "assistant", "content": item.respond})

        if len(history) == 0:
            messages.append(
                {
                    "role": "user",
                    "content": self.__generate_system_prompt(prompt) + prompt,
                }
            )
        else:
            messages.append({"role": "user", "content": prompt})

        return messages

    def _ask(self, messages: list) -> Generator[str, None, None]:
        self.response = ""
        self.stream_queue = asyncio.Queue()

        self.messages = messages

        ws = websocket.WebSocketApp(
            self._create_url(),
            on_message=self.__on_message,
            on_error=self.__on_error,
            on_close=self.__on_close,
        )
        ws.on_open = self.__on_open

        if self.stream:
            threading.Thread(
                target=ws.run_forever, kwargs={"sslopt": {"cert_reqs": ssl.CERT_NONE}, "ping_timeout": 10}, daemon=True
            ).start()
            while True:
                try:
                    content = self.stream_queue.get_nowait()
                    if content is None:  # 流结束
                        break
                    yield content
                except asyncio.QueueEmpty:
                    time.sleep(0.01)
        else:
            ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_timeout=10)
            yield self.response

    async def _ask_sync(self, messages: list) -> str:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, partial(self._ask, messages=messages))
        return "".join(result)  # 转换生成器结果为字符串

    async def _ask_stream(self, messages: list) -> AsyncGenerator[str, None]:
        async def sync_to_async_generator():
            loop = asyncio.get_event_loop()
            generator = await loop.run_in_executor(None, partial(self._ask, messages=messages))
            for chunk in generator:
                yield chunk

        return sync_to_async_generator()

    @overload
    async def ask(
        self,
        prompt: str,
        history: List[Message],
        images: Optional[List[str]] = [],
        tools: Optional[List[dict]] = [],
        stream: Literal[False] = False,
        **kwargs,
    ) -> str: ...

    @overload
    async def ask(
        self,
        prompt: str,
        history: List[Message],
        images: Optional[List[str]] = [],
        tools: Optional[List[dict]] = [],
        stream: Literal[True] = True,
        **kwargs,
    ) -> AsyncGenerator[str, None]: ...

    async def ask(
        self,
        prompt: str,
        history: List[Message],
        images: Optional[List[str]] = [],
        tools: Optional[List[dict]] = [],
        stream: Optional[bool] = False,
        **kwargs,
    ) -> Union[AsyncGenerator[str, None], str]:
        """
        多模态：图像识别

        :param image_path: 图像路径
        :return: 识别结果
        """
        messages = self._build_messages(prompt, history, images)

        if stream:
            return await self._ask_stream(messages)

        return await self._ask_sync(messages)
