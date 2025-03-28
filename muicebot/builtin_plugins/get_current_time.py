from muicebot.plugin import PluginMetadata
from muicebot.plugin.func_call import on_function_call

__metadata__ = PluginMetadata(
    name="time", description="时间插件", usage="直接调用，返回 %Y-%m-%d %H:%M:%S 格式的当前时间"
)


@on_function_call(
    description="获取当前时间",
)
async def get_current_time() -> str:
    """
    获取当前时间
    """
    import datetime

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return current_time
