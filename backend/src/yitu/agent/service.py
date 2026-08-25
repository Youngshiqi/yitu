"""旧导入路径兼容层。

新代码应从 :mod:`yitu.agent.api_service` 导入 API 会话门面；保留本模块
是为了不破坏已有扩展和测试的导入路径。
"""

from yitu.agent.api_service import AgentConversationService

__all__ = ["AgentConversationService"]
