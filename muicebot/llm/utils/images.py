import base64
from typing import Optional


def get_image_base64(local_path: Optional[str] = None, image_bytes: Optional[bytes] = None) -> str:
    """
    获取本地图像 Base64 的方法
    """
    if local_path:
        with open(local_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
            return image_data
    if image_bytes:
        image_base64 = base64.b64encode(image_bytes)
        return image_base64.decode("utf-8")
    raise ValueError("You must pass in a valid parameter!")
