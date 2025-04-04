# 快速开始💻

本节及后续文档默认您有独立搭建过 Nonebot 服务的相关经验。

建议环境：

- Python 3.10 及以上 Python 版本

- 一个已经存在的 Nonebot 项目，参见： [快速上手 | Nonebot](https://nonebot.dev/docs/quick-start#%E5%88%9B%E5%BB%BA%E9%A1%B9%E7%9B%AE)


## 安装插件⚙️

由于此插件还在开发早期，因此请通过 `pip` 手动安装插件：

```shell
pip install muicebot
```

手动编辑 Nonebot 项目中的 `pyproject.toml`, 在 `[tool.nonebot]` 部分追加插件:

```toml
plugins = ["muicebot"]
```


## 适配器配置🔧

如一切顺利，我们可以开始 Nonebot 适配器的配置：

在项目中创建 `.env` 文件并写入：

```dotenv
DRIVER=~fastapi+~websockets+~httpx
```

这只是 NoneBot 运行的必需项，接下来我们将配置适配器。

如果你使用 OneBot 适配器，则无需另行配置，在平台实现中配置连接即可。除非你想[配置访问权限](https://onebot.adapters.nonebot.dev/docs/guide/configuration) 。

如果你使用 Telegram 适配器，请写入 Bot 密钥，如需要，也可写入代理配置：

```dotenv
telegram_bots = [{"token": "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHI"}]
telegram_proxy = "http://127.0.0.1:10809"
```

如果你使用 QQ 适配器，请参考[文档示例](https://github.com/nonebot/adapter-qq)填写信息。下面给出了私域频道机器人（审核未通过沙盒版）的示例配置：

```dotenv
QQ_IS_SANDBOX=true
QQ_BOTS='[{"id": "11451419", "token": "KFCvivo50MuxueYYDS", "secret": "GiveAStarToMuice5Q", "intent": {"guild_messages": true,"at_messages": true}, "use_websocket": true}]'
```

## 响应昵称配置🧸

正常情况下，MuiceBot 只会处理 `at_event` 事件或者是指令事件，对于某些客户端来说 @bot 的操作还是太麻烦了，有没有更加简单的方法？

有的兄弟，有的。我们可以定义一个响应前缀来让沐雪响应消息事件。

在 `.env` 文件中配置：

```dotenv
MUICE_NICKNAMES=["沐雪", "muice", "雪"]
```

这将响应前缀为“沐雪”、“muice”、“雪”的消息事件，且无需在响应前缀后面加入空格分隔符，比如下列的消息将被沐雪响应：

> 雪，我只会对你动心你知道吗

> 唔...真的嘛？（脸红）

## 超级用户

超级用户可以执行例如 `.load` 之类改变机器人运行方式的指令，在配置文件中设置用户ID可以将其设为超级用户：

```dotenv
SUPERUSERS=["123456789"]
```

> [!NOTE]
>
> 用户 ID 不一定是平台上显示的 ID ，比如 QQ 频道中的用户 ID 就不是 QQ 号。对此我们推荐你使用 `.whoami` 指令获取当前会话 ID ，而最后一段数字就是你的真实用户 ID

## 自定义插件目录/启用内嵌插件

从以下目录中加载 Nonebot2 或 Muicebot 插件，默认为空列表：

```dotenv
PLUGINS_DIR=["./plugins"]
ENABLE_BUILTIN_PLUGINS=true
```

至此，`NoneBot` 的本身的配置部分到此结束