import re
from typing import Literal

inside_think = False


def process_thoughts(message: str, status: Literal[0, 1, 2] = 1) -> tuple[str, str]:
    """
    思维过程提取优化

    :param message: 消息内容
    :param status: 思维链处理状态 (0: 无需处理，直接返回； 1: 提取思考过程并单独成段； 2: 仅输出思考结果)
    """
    if not status:
        return ("", message)

    thoughts_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
    thoughts_match = thoughts_pattern.search(message)
    thoughts = thoughts_match.group(1) if thoughts_match else ""

    if thoughts == "\n\n":
        thoughts = ""
    else:
        thoughts = thoughts.replace("\n", "")

    result = thoughts_pattern.sub("", message).strip()

    if status == 2 or not thoughts:
        return ("", result)

    return (f"思考过程：{thoughts}", f"{result}")


def stream_process_thoughts(chunk: str, status: Literal[0, 1, 2] = 1) -> str:
    """
    流式思维过程提取优化

    :param message: 消息内容
    :param status: 思维链处理状态 (0: 无需处理，直接返回； 1: 提取思考过程并单独成段； 2: 仅输出思考结果)
    """
    global inside_think

    if not status:
        return chunk

    inside_think = False

    if status == 2:
        if "<think>" in chunk:
            inside_think = True
            chunk = chunk.replace("<think>", "")

        if "</think>" in chunk:
            inside_think = False
            chunk = chunk.replace("</think>", "")

        if inside_think:
            return ""

        return chunk

    chunk = chunk.replace("<think>", "思考过程：").replace("</think>", "\n\n")
    return chunk
