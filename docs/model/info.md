# 模型加载器信息

## 实现的加载器及其支持的模型

我们目前实现了以下模型加载器:

| 模型加载器                                                   | 介绍                                                         | 支持的模型列表                                               |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| [Azure](https://github.com/Moemu/MuiceBot/tree/main/Muice/llm/Azure.py) | 可调用 [GitHub Marketplace ](https://github.com/marketplace/models)中的在线模型 | [*模型列表*](https://github.com/marketplace?type=models)     |
| [Dashscope](https://github.com/Moemu/MuiceBot/tree/main/Muice/llm/Dashscope.py) | 可调用阿里云百炼平台的在线模型                               | [*模型列表*](https://help.aliyun.com/zh/model-studio/getting-started/models) |
| [Llmtuner](https://github.com/Moemu/MuiceBot/tree/main/Muice/llm/Llmtuner.py) | 可调用 [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory/tree/main) 支持的模型 | [*模型列表*](https://github.com/hiyouga/LLaMA-Factory/blob/main/README_zh.md#模型) |
| [Ollama](https://github.com/Moemu/MuiceBot/tree/main/Muice/llm/Ollama.py) | 使用 Ollama Python SDK 访问 Ollama 接口，需要提前启动模型服务 | [*模型列表*](https://ollama.com/search)                      |
| [Openai](https://github.com/Moemu/MuiceBot/tree/main/Muice/llm/Openai.py) | 可调用 OpenAI API 格式的接口，支持 DeepSeek 官方API          | *any*                                                        |
| [Rwkv](https://github.com/Moemu/MuiceBot/tree/main/Muice/llm/Rwkv.py) | 使用 [RWKV-Runner](https://github.com/josStorer/RWKV-Runner) 提供的 API 服务访问 RWKV 模型 | *RWKV-any*                                                   |
| [Transformers](https://github.com/Moemu/MuiceBot/tree/main/Muice/llm/Transformers.py) | 使用 transformers 方案加载, 适合通过 P-tuning V2 方式微调的模型 | ChatGLM                                                      |
| [Xfyun](https://github.com/Moemu/MuiceBot/tree/main/Muice/llm/Xfyun.py) | 可调用由 [星火大模型精调平台](https://training.xfyun.cn/) 微调的在线模型 | [*模型列表*](https://training.xfyun.cn/modelSquare)          |

对于不同的加载器，可能需要额外的依赖，请根据报错提示安装。

有关各个模型加载器的配置，参见 [模型加载器配置](/model/configuration.md)

## 加载器功能支持列表

本页面将向您展示目前所有模型加载器支持功能的情况，以便帮助您更好的配置模型

| 模型加载器       | 多轮对话 | 多模态：单图片识别 | 多模态：多图片识别 | 推理模型调用 | 工具调用 | 流式对话 |
| ---------------- | -------- | ------------------ | ------------------ | ------------ | -------- | -------- |
| `Azure`          | ✅        | 🚧                  | 🚧                  | ⭕            | 🚧        | ✅        |
| `Dashscope`      | ✅        | ✅                  | ✅                  | ✅            | 🚧        | ✅        |
| `Llmtuner`       | ✅        | 🚧                  | 🚧                  | 🚧            | 🚧        | ❓        |
| `Ollama`         | ✅        | 🚧                  | 🚧                  | 🚧            | 🚧        | ✅        |
| `Openai`         | ✅        | 🚧                  | 🚧                  | ✅            | 🚧        | ✅        |
| `Transformers`   | ✅        | 🚧                  | 🚧                  | 🚧            | 🚧        | ✅        |
| `Xfyun(ws)`      | ✅        | ❌                  | ❌                  | ✅            | ❌        | ✅        |
| `Xfyun(sparkai)` | 🚧        | 🚧                  | ❌                  | 🚧            | 🚧        | 🚧        |

✅：表示此加载器能很好地支持该功能并且 `MuiceBot` 已实现

⭕：表示此加载器虽支持该功能，但可能引发类型检查错误或仅基本兼容该功能

🚧：表示此加载器虽然支持该功能，但 `MuiceBot` 未实现或正在实现中

❓：表示 Maintainer 暂不清楚此加载器是否支持此项功能，可能需要进一步翻阅文档和检查源码

❌：表示此加载器不支持该功能