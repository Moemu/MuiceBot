import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class Message:
    id: int | None = None
    """每条消息的唯一ID"""
    time: str = datetime.strftime(datetime.now(), "%Y.%m.%d %H:%M:%S")
    """
    字符串形式的时间数据：%Y.%m.%d %H:%M:%S
    若要获取格式化的 datetime 对象，请使用 format_time
    """
    userid: str = ""
    """Nonebot 的用户id"""
    message: str = ""
    """消息主体"""
    respond: str = ""
    """模型回复（不包含思维过程）"""
    history: int = 1
    """消息是否可用于对话历史中，以整数形式映射布尔值"""
    images: List[str] = field(default_factory=list)
    """多模态中使用的图像，默认为空列表"""

    def __post_init__(self):
        if isinstance(self.images, str):
            self.images = json.loads(self.images)
        elif self.images is None:
            self.images = []

    @property
    def format_time(self) -> datetime:
        """将时间字符串转换为 datetime 对象"""
        return datetime.strptime(self.time, "%Y.%m.%d %H:%M:%S")

    # 又臭又长的比较函数
    def __lt__(self, other: "Message") -> bool:
        return self.format_time < other.format_time

    def __le__(self, other: "Message") -> bool:
        return self.format_time <= other.format_time

    def __gt__(self, other: "Message") -> bool:
        return self.format_time > other.format_time

    def __ge__(self, other: "Message") -> bool:
        return self.format_time >= other.format_time
