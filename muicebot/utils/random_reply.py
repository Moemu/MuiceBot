from datetime import datetime
from random import random
from re import split

from muicebot.config import plugin_config


def time_to_minutes(time_str):
    """将时间字符串转换为当天的总分钟数"""
    hh, mm = map(int, time_str.split(':'))
    return hh * 60 + mm


class RandomReply:
    def __init__(self) -> None:
        # 活跃时间相关配置项
        self.unactive_coefficient: float = plugin_config.unactive_coefficient
        self.active_coefficient: float = plugin_config.active_coefficient
        self.time_ranges: list = plugin_config.active_time_ranges

        self.private_last_message: dict = {}

        # 群组相关配置项
        self.group_last_message: dict = {}
        self.including_words: list = plugin_config.including_nicknames
        self.including_trigger_coefficient: float = plugin_config.including_nicknames_trigger_coefficient
        self.beginning_trigger_words: list = plugin_config.beginning_trigger_words
        self.beginning_trigger_coefficient: float = plugin_config.beginning_trigger_coefficient
        self.random_trigger_probability_coefficient: float = plugin_config.random_trigger_probability_coefficient

        self.user_coefficient: dict = {}  # 用户亲密度相关系数

    def private_reply(self, userid, message) -> bool:
        """通过随机数和用户信息判断是否回复"""
        """通过随机数和群聊信息判断是否回复"""
        now = datetime.now()
        now_str = now.strftime("%H:%M")
        time_coefficient = self.active_coefficient if self.is_time_in_range(now_str) else self.unactive_coefficient

        # 尝试获取上次消息的时间戳
        last_message_time = self.private_last_message.get(userid)

        # 计算时间差值
        if last_message_time:
            time_difference = (now - last_message_time).total_seconds() / 60
        else:
            time_difference = float('inf')  # 如果没有上次消息时间，则设为无穷大

        # 根据时间差值设置 activity _coefficient
        if time_difference <= 3:
            activity_coefficient = 0.45
        else:
            activity_coefficient = 0

        user_coefficient = self.user_coefficient.get(userid)
        if user_coefficient is None:
            user_coefficient = 1.0

        comprehensive_coefficient = (time_coefficient + activity_coefficient) * user_coefficient
        if random() <= comprehensive_coefficient:
            return True
        return False

    # 逻辑没想好

    def group_reply(self, userid, groupid, message) -> bool:
        """通过随机数和群聊信息判断是否回复"""
        now = datetime.now().strftime("%H:%M")
        time_coefficient = self.active_coefficient if self.is_time_in_range(now) else self.unactive_coefficient

        # 尝试获取上次消息的时间戳
        last_message_time = self.group_last_message.get(groupid)

        # 计算时间差值
        if last_message_time:
            time_difference = (now - last_message_time).total_seconds() / 60
        else:
            time_difference = 0  # 如果没有上次消息时间，则设为无穷大

        # 根据时间差值设置 activity _coefficient
        if time_difference <= 0.2:
            activity_coefficient = 0.2
        else:
            activity_coefficient = 0

        user_coefficient = self.user_coefficient.get(userid)
        if user_coefficient is None:
            user_coefficient = 1.0

        # 综合系数
        comprehensive_coefficient = (time_coefficient + activity_coefficient) * user_coefficient

        # 太长的消息不看!
        if len(message) >= 100:
            if random() <= self.random_trigger_probability_coefficient * comprehensive_coefficient:
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
                        if (content in sentence and
                                random() <= self.beginning_trigger_coefficient * comprehensive_coefficient):
                            return True

        # 句中出现触发词触发
        for content in self.including_words:
            if content in message:
                if random() <= self.including_trigger_coefficient * comprehensive_coefficient:
                    return True

        # 随机触发
        if random() <= self.random_trigger_probability_coefficient * comprehensive_coefficient:
            return True

        return False

    def at_reply(self, userid, groupid, message) -> bool:
        """判断At消息是否回复"""
        """通过随机数和群聊信息判断是否回复"""
        now = datetime.now().strftime("%H:%M")
        time_coefficient = self.active_coefficient if self.is_time_in_range(now) else self.unactive_coefficient

        # 尝试获取上次消息的时间戳
        last_message_time = self.group_last_message.get(groupid)

        # 计算时间差值
        if last_message_time:
            time_difference = (now - last_message_time).total_seconds() / 60
        else:
            time_difference = 0  # 如果没有上次消息时间，则设为无穷大

        # 根据时间差值设置 activity _coefficient
        if time_difference <= 0.5:
            activity_coefficient = 0.2
        else:
            activity_coefficient = 0

        user_coefficient = self.user_coefficient.get(userid)
        if user_coefficient is None:
            user_coefficient = 1.0

        comprehensive_coefficient = (time_coefficient + activity_coefficient) * user_coefficient
        if random() <= comprehensive_coefficient:
            return True
        return False

    # tool
    def is_time_in_range(self, input_time) -> bool:
        """
        检查输入时间是否在配置的时间范围内
        :param input_time: 字符串，格式为"HH:MM"
        :return: 布尔值，表示时间是否在范围内
        """
        input_min = time_to_minutes(input_time)

        for start_str, end_str in self.time_ranges:
            start = time_to_minutes(start_str)
            end = time_to_minutes(end_str)

            # 处理跨天时间范围（如22:00-02:00）
            if start <= end:
                if start <= input_min < end:
                    return True
            else:
                if input_min >= start or input_min < end:
                    return True

        return False
