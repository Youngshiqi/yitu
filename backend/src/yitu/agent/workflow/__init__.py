"""单主图 LangGraph 工作流。

注意：不要在包初始化时 eager 导入 ``assistant_graph``。

图装配会间接依赖 runtime 与 capabilities，而 capabilities 又会导入
``workflow.contracts``；若在这里 ``from ...assistant_graph import ...``，
Python 初始化包时就会形成 ``workflow → assistant_graph → runtime →
capabilities → workflow`` 的循环导入。调用方一律使用全路径导入：

    from yitu.agent.workflow.assistant_graph import build_assistant_graph
"""

__all__ = ["build_assistant_graph"]


def __getattr__(name: str):
    # 惰性暴露，仅在显式 ``from yitu.agent.workflow import build_assistant_graph``
    # 时才加载图装配模块，避免包初始化阶段的循环导入。
    if name == "build_assistant_graph":
        from yitu.agent.workflow.assistant_graph import build_assistant_graph

        return build_assistant_graph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
