"""检索质量评估：golden set 定义与 hit@k / MRR@k 指标。

评估命中规则：返回的 citation 内容包含任一期望子串即视为命中。
该模块不依赖数据库，可被评估脚本和单元测试共同复用。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """一条评估用例：口语化查询 -> 期望命中的内容片段（任一命中即可）。"""

    query: str
    expect_substrings: tuple[str, ...]
    note: str = ""
    tags: frozenset[str] = field(default=frozenset())


# 基线 golden set：基于已发布的《禁止寄递物品管理规定》及其指导目录。
# 覆盖三类查询形态：列举型、口语物品型、条款责任型。
GOLDEN_SET: tuple[GoldenCase, ...] = (
    GoldenCase(
        "哪些东西不能寄",
        ("危害国家安全、扰乱社会秩序", "以下简称禁寄物品"),
        note="总则类：应命中第三条禁寄物品定义",
        tags=frozenset({"enumeration"}),
    ),
    GoldenCase(
        "禁寄物品具体清单在哪里看",
        ("指导目录",),
        note="指路类：应命中附录指导目录引用",
        tags=frozenset({"enumeration"}),
    ),
    GoldenCase(
        "烟花爆竹可以寄吗",
        ("烟花爆竹", "鞭炮"),
        note="物品类：应命中爆炸物品目录",
        tags=frozenset({"colloquial"}),
    ),
    GoldenCase(
        "鞭炮能上快递吗",
        ("鞭炮", "烟花爆竹"),
        note="口语变体：与上一条同目标，验证词汇鲁棒性",
        tags=frozenset({"colloquial"}),
    ),
    GoldenCase(
        "匕首弹簧刀可以寄吗",
        ("管制刀具", "弹簧刀"),
        note="物品类：应命中管制器具目录",
        tags=frozenset({"colloquial"}),
    ),
    GoldenCase(
        "汽油柴油能寄吗",
        ("汽油、柴油", "煤油"),
        note="物品类：应命中易燃液体目录",
        tags=frozenset({"colloquial"}),
    ),
    GoldenCase(
        "酒精可以快递吗",
        ("酒精", "松香油"),
        note="物品类：应命中易燃液体目录",
        tags=frozenset({"colloquial"}),
    ),
    GoldenCase(
        "蓄电池可以寄吗",
        ("蓄电池", "腐蚀性物质"),
        note="物品类：应命中腐蚀性物质目录",
        tags=frozenset({"colloquial"}),
    ),
    GoldenCase(
        "压缩氧气氦气能寄吗",
        ("压缩氧气", "气雾剂"),
        note="物品类：应命中压缩气体目录",
        tags=frozenset({"colloquial"}),
    ),
    GoldenCase(
        "象牙虎骨犀牛角可以寄吗",
        ("象牙、虎骨", "犀牛角"),
        note="物品类：应命中濒危野生动物目录",
        tags=frozenset({"colloquial"}),
    ),
    GoldenCase(
        "高仿假包能寄吗",
        ("假冒伪劣", "侵犯知识产权"),
        note="口语转术语：高仿 -> 假冒伪劣",
        tags=frozenset({"colloquial", "vocabulary-gap"}),
    ),
    GoldenCase(
        "电脑坏了里面有锂电池能寄吗",
        ("锂电池", "蓄电池", "易燃"),
        note="词汇鸿沟用例：文档无锂电池，期望泛化命中相关危险品条目",
        tags=frozenset({"vocabulary-gap"}),
    ),
    GoldenCase(
        "发现枪支弹药应该怎么办",
        ("发现各类枪支", "弹药"),
        note="处置类：应命中第十一条（一）",
        tags=frozenset({"clause"}),
    ),
    GoldenCase(
        "发现毒品要报告哪个部门",
        ("发现各类毒品", "公安机关"),
        note="处置类：应命中第十一条（二）",
        tags=frozenset({"clause"}),
    ),
    GoldenCase(
        "用户夹带禁寄物品会怎么处罚",
        ("夹带", "匿报"),
        note="责任类：应命中第十六条",
        tags=frozenset({"clause"}),
    ),
    GoldenCase(
        "快递公司要公示禁寄规定吗",
        ("公示",),
        note="义务类：应命中第六条",
        tags=frozenset({"clause"}),
    ),
    GoldenCase(
        "这个规定什么时候开始施行",
        ("施行",),
        note="元信息类：应命中第十七条",
        tags=frozenset({"clause"}),
    ),
    GoldenCase(
        "企业收寄时发现禁寄物品怎么处置",
        ("停止发运", "处置预案"),
        note="流程类：应命中第十/十一条",
        tags=frozenset({"clause"}),
    ),
)


def first_hit_rank(case: GoldenCase, results: list[str]) -> int | None:
    """返回首个命中结果的排名（1-based）；未命中返回 None。"""
    for rank, content in enumerate(results, start=1):
        if any(token in content for token in case.expect_substrings):
            return rank
    return None


def evaluate_results(
    cases: tuple[GoldenCase, ...],
    results_per_case: list[list[str]],
    *,
    k: int = 5,
) -> dict[str, float]:
    """基于已收集的检索结果计算 hit@k 与 MRR@k（同步纯函数，便于单测）。"""
    if len(cases) != len(results_per_case):
        raise ValueError("cases and results must align")
    hits = 0
    reciprocal_ranks: list[float] = []
    for case, results in zip(cases, results_per_case, strict=True):
        rank = first_hit_rank(case, results[:k])
        if rank is not None:
            hits += 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)
    total = len(cases)
    return {
        "hit@k": hits / total if total else 0.0,
        "mrr@k": sum(reciprocal_ranks) / total if total else 0.0,
        "cases": float(total),
        "hits": float(hits),
    }
