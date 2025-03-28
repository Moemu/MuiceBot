import inspect
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from .typing import ASYNC_FUNCTION_CALL_FUNC, SYNC_FUNCTION_CALL_FUNC


def path_to_module_name(module_path: Path) -> str:
    """
    获取模块包名的方法
    """
    rel_path = module_path.resolve().relative_to(Path.cwd().resolve())
    if rel_path.stem == "__init__":
        return ".".join(rel_path.parts[:-1])
    else:
        return ".".join(rel_path.parts[:-1] + (rel_path.stem,))


def is_coroutine_callable(call: Callable[..., Any]) -> bool:
    """
    检查 call 是否是一个 callable 协程函数
    """
    if inspect.isroutine(call):
        return inspect.iscoroutinefunction(call)
    if inspect.isclass(call):
        return False
    func_ = getattr(call, "__call__", None)
    return inspect.iscoroutinefunction(func_)


def async_wrap(func: SYNC_FUNCTION_CALL_FUNC) -> ASYNC_FUNCTION_CALL_FUNC:
    """
    装饰器，将同步函数包装为异步函数
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    return wrapper  # type: ignore
