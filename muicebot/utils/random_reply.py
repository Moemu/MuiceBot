from random import random
from re import split

from muicebot.config import plugin_config


class RandomReply:
    def __init__(self) -> None:
        self.private_last_message: dict = {}

        # 群组相关配置项
        self.group_last_message: dict = {}
        self.including_words: list = plugin_config.including_nicknames
        self.including_trigger_coefficient: float = plugin_config.including_nicknames_trigger_coefficient
        self.beginning_trigger_words: list = plugin_config.beginning_trigger_words
        self.beginning_trigger_coefficient: float = plugin_config.beginning_trigger_coefficient
        self.random_trigger_probability_coefficient: float = plugin_config.random_trigger_probability_coefficient

    def private_reply(self, userid, message) -> bool:
        return True

    # 逻辑没想好

    def group_reply(self, userid, groupid, message) -> bool:
        # 太长的消息不看!
        if len(message) >= 100:
            if random() <= self.random_trigger_probability_coefficient:
                return True
            else:
                return False

        # 句首出现触发词触发
        sentences = split(r'[。！？\s ,.?]', message)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            for trigger_word in self.beginning_trigger_words:
                if sentence.startswith(trigger_word):
                    for content in self.beginning_trigger_words:
                        if content in sentence and random() <= self.beginning_trigger_coefficient:
                            return True

        # 句中出现触发词触发
        for content in self.including_words:
            if content in message:
                if random() <= self.including_trigger_coefficient:
                    return True

        # 随机触发
        if random() <= self.random_trigger_probability_coefficient:
            return True

        return False
