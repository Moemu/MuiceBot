## 介绍✨

沐雪，一只会**主动**找你聊天的 AI 女孩子，其对话模型基于 [Qwen](https://github.com/QwenLM) 微调而成，训练集体量 3k+ ，具有二次元女孩子的说话风格，比较傲娇，但乐于和你分享生活的琐碎，每天会给你不一样的问候。

## 功能🪄

✅ 内嵌多种模型加载器，比如 [Llmtuner](https://github.com/hiyouga/LLaMA-Factory) 和 [OpenAI](https://platform.openai.com/docs/overview) ，可加载市面上大多数的模型服务或本地模型，部分支持多模态（图片识别）。另外还附送只会计算 3.9 > 3.11 的沐雪 Roleplay 微调模型一枚~

✅ 使用 `nonebot_plugin_alconna` 作为通用信息接口，支持市面上的大多数适配器，当然也对一些常见的适配器做了优化

✅ 支持基于 `nonebot_plugin_apscheduler` 的定时任务，可定时向大语言模型交互或直接发送信息

✅ 支持基于 `nonebot_plugin_alconna` 的几条常见指令。什么，没有群管理指令？下次再说吧（bushi）

✅ 使用 SQLite3 保存对话数据。那有人就要问了：Maintainer，Maintainer，能不能实现长期短期记忆、LangChain、FairSeq 这些记忆优化啊，实在不行，多模态图像数据保存和最大记忆长度总该有吧。很抱歉，都没有（

## TODO📝

- [X] Function Call 插件系统

- [X] 多模态模型：工具集支持

- [ ] OFA 图像识别。既然都有了多模态为什么还用 OFA？好吧，因为没钱调用接口

- [ ] Faiss 记忆优化。沐雪总记不太清楚上一句话是什么

- [ ] 短期记忆和长期记忆优化。总感觉这是提示工程师该做的事情，~~和 Bot 没太大关系~~

- [ ] （多）对话语音合成器。比如 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) 、[RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)之类的。

- [ ] 发布。我知道你很急，但是你先别急。


近期更新路线：[MuiceBot 更新计划](https://github.com/users/Moemu/projects/2)

## 本项目适合谁？

- 拥有编写过 Python 程序经验的开发者

- 搭建过 Nonebot 项目的 bot 爱好者

- 想要随时随地和大语言模型交互并寻找着能够同时兼容市面上绝大多数 SDK 的机器人框架的 AI 爱好者