import importlib
import sys

import nonebot
from nonebot.drivers import Driver


def load_specified_adapter(driver: Driver, adapter: str):
    """
    加载指定的 Nonebot 适配器
    """
    try:
        module = importlib.import_module(adapter)
        adapter = module.Adapter
        driver.register_adapter(adapter)  # type: ignore
    except ImportError:
        print(f"\33[35m{adapter}不存在，请检查拼写错误或是否已安装该适配器？")
        sys.exit(1)


nonebot.init()

driver = nonebot.get_driver()

enable_adapters: list[str] = driver.config.model_dump().get("enable_adapters", [])

for adapter in enable_adapters:
    load_specified_adapter(driver, adapter)

nonebot.load_plugin("muicebot")

nonebot.run()
