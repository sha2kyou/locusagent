"""HTTP 中间件。"""

from .auth_isolation import install_auth_isolation

__all__ = ["install_auth_isolation"]
