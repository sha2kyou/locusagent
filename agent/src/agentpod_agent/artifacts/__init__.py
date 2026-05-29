"""产物模块：用户可自定义类目（子菜单）+ 产物条目（标题/内容/时间）。"""

from .store import (
    create_artifact,
    create_category,
    delete_artifact,
    delete_category,
    get_artifact,
    list_artifacts,
    list_categories,
    recall_artifacts,
    resolve_category_id,
    update_artifact,
)

__all__ = [
    "create_artifact",
    "create_category",
    "delete_artifact",
    "delete_category",
    "get_artifact",
    "list_artifacts",
    "list_categories",
    "recall_artifacts",
    "resolve_category_id",
    "update_artifact",
]
