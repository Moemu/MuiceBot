# 插件开发

## 开发 Nonebot2 插件

本项目完全兼容基于原生 Nonebot2 开发的插件，您只需要将编写好的插件放入 `muicebot/plugins` 中即可，Bot 启动时会自动加载其中的插件。

## 开发 Function Call 插件

工具调用是目前主流大语言模型的重要能力之一，使用工具函数，AI可以获得操作现实的能力并协助我们完成更多的日常任务。

让我们从获取天气的 `weather.py` 开始。

### 第一个插件

在 `muicebot/plugins` 下创建 `weather.py` 文件，填入：

```python
from muicebot.plugin import PluginMetadata
from muicebot.plugin.func_call import on_function_call
from muicebot.plugin.func_call.parameter import String

__metadata__ = PluginMetadata(
    name="muicebot-plugin-weather",
    description="获取天气",
    usage="在配置文件中配置好 api_key 后通过 function_call 调用"
)

@on_function_call(description="可以用于查询天气").params(
    location = String(description="城市。(格式:城市英文名,国家两位大写英文简称)", required=True)
)
async def get_weather(location: str) -> str:
    # 这里可以调用天气API查询天气，这里只是一个简单的示例
    return f"{location}的天气是晴天, 温度是25°C"
```

尽管这与 Nonebot 的插件编写基本一致，但这里还是有几个要点：

- 通过 `muicebot.plugin.PluginMetadata` 撰写插件元数据

- 通过 `@on_function_call` 装饰器注册可供 AI 直接调用的 `function_call` 函数。这里我们需要填写一个参数：

    - `description` 函数描述。这个字段会被传入到模型加载器的 `tools` 列表，来给 AI 决定何时调用

- 通过装饰器的 `params` 方法定义函数参数（可选）

- **必须** 使用异步函数作为被修饰函数，无论是否有异步调用

### 依赖注入

MuiceBot 的 Function_call 插件支持 NoneBot2 原生的会话上下文依赖注入（暂不支持 `T_State`）:

- Event 及其子类实例
- Bot 及其子类实例
- Matcher 及其子类实例

下面让我们使用依赖注入来给我们的 `weather.py` 添加一个简单获取用户名的功能

```python
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v12 import Bot as Onebotv12Bot

from muicebot.plugin import PluginMetadata
from muicebot.plugin.func_call import on_function_call

# 省略部分代码...

async def get_username(bot: Bot, event: Event) -> str:
    '''
    根据具体适配器实现获取用户名
    '''
    userid = event.get_user_id()
    username = ""

    if isinstance(bot, Onebotv12Bot):
        userinfo = await bot.get_user_info(user_id=userid)
        username = userinfo.get("user_displayname", userid)

    if not username:
        username = userid

    return username

@on_function_call(description="可以用于查询天气").params(
    location = String(description="城市。(格式:城市英文名,国家两位大写英文简称)", required=True)
)
async def get_weather(location: str, bot: Bot, event: Event) -> str:
    username = await get_username(bot, event)
    return f"{username}你好，{location}的天气是晴天, 温度是25°C"
```

### 配置文件

现在，我们的天气函数只能返回固定的字段，还未能调用真实的 API 接口来获取更详细的天气信息。

为了使用 API 接口，我们需要 API Key，这时我们可以使用配置文件来安全地存储密钥。

新建 config.py ，填写：

```python
from pydantic import BaseModel, field_validator

class ScopeConfig(BaseModel):
    api_key: str
    base_url: str = "https://api.openweathermap.org/data/2.5/weather"

class Config(BaseModel):
    weather: ScopeConfig
```

MuiceBot 的插件配置模型写法和 Nonebot 模型写法是一样的，但这里我们使用了 scope 配置。事实上，对于 MuiceBot ，我们推荐使用 scope 配置而避免在配置项前填写长长的插件前缀。

理由很简单，参见：[配置文件](/guide/configuration)

然后像正常的 Nonebot 插件一样，加载插件配置即可。

参考 openweathermap 的接口文档，在 weather.py 中写入：

```python
from muicebot.plugin import on_function_call, String
from nonebot import logger
from nonebot import get_plugin_config
from .config import Config
import httpx

plugin_config = get_plugin_config(Config).weather # 获取插件配置

@on_function_call(description="可以用于查询天气").params(
    location = String(description="城市。(格式:城市英文名,国家两位大写英文简称)", required=True)
)
async def get_weather(location: str) -> str:
    """查询指定地点的天气信息"""
    base_url = plugin_config.base_url

    # 构建请求参数
    params = {
        "q": location,
        "appid": plugin_config.api_key,
        "units": "metric",  # 摄氏温度
        "lang": "zh_cn"     # 中文
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, params=params, timeout=10)

            if response.status_code != 200:
                logger.error(f"请求失败: {response.status_code} - {response.text}")
                return f"获取天气信息失败：{response.status_code}"

            data = response.json()

            # 解析返回的天气数据
            city = data.get("name", location)
            weather_desc = data["weather"][0]["description"]
            temp = data["main"]["temp"]
            humidity = data["main"]["humidity"]
            wind_speed = data["wind"]["speed"]

            # 格式化天气信息
            result = (
                f"{city} 的天气：\n"
                f"天气：{weather_desc}\n"
                f"温度：{temp}°C\n"
                f"湿度：{humidity}%\n"
                f"风速：{wind_speed} m/s"
            )
            return result

    except httpx.HTTPError as e:
        logger.error(f"HTTP请求异常: {str(e)}")
        return "获取天气信息失败，请稍后再试。"
    except Exception as e:
        logger.error(f"出现异常: {str(e)}")
        return "查询天气时发生错误，请检查日志。"
```

配置好后就可以运行了。你看，很简单不是吗？