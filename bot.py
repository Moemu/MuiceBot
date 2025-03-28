import nonebot
import yaml
from nonebot.adapters.onebot.v11 import Adapter as Adapterv11
from nonebot.adapters.onebot.v12 import Adapter as Adapterv12
from nonebot.adapters.qq import Adapter as QQAdapter
from nonebot.adapters.telegram import Adapter as TelegramAdapter
from nonebot.config import Config

PLUGINS_CONFIG_PATH = "./configs/plugins.yml"


def load_yaml_config() -> dict:
    """
    插件优先加载 YAML 配置，失败则返回空字典
    """
    try:
        with open(PLUGINS_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}


nonebot.init()

driver = nonebot.get_driver()

yaml_config = load_yaml_config()
env_config = driver.config.model_dump()
final_config = {**env_config, **yaml_config}  # 合并配置，yaml优先
driver.config = Config(**final_config)

driver.register_adapter(Adapterv12)
driver.register_adapter(Adapterv11)
driver.register_adapter(TelegramAdapter)
driver.register_adapter(QQAdapter)

nonebot.load_plugin("muicebot")

nonebot.run()
