"""检索质量评估：对已发布知识库跑 golden set，输出 hit@5 / MRR@5。

用法：
    python scripts/eval_retrieval.py            # 基线（纯混合检索）
    python scripts/eval_retrieval.py --enhanced # 基线 + 查询改写 + LLM 精排

--enhanced 需要配置生产对话模型（openai-compatible/deepseek）；
未配置时自动跳过增强组，只输出基线。
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select

from yitu.knowledge.evaluation import GOLDEN_SET, evaluate_results, first_hit_rank
from yitu.knowledge.models import DocumentStatus, KnowledgeDocument
from yitu.knowledge.retrieval import KnowledgeRetriever
from yitu.platform.database import SessionFactory

K = 5


async def collect_results(enhanced: bool) -> tuple[list[list[str]], list[tuple[str, int | None]]]:
    """返回每个用例的检索内容列表与首个命中排名（供逐条展示）。"""
    rewriter = reranker = None
    if enhanced:
        from yitu.agent.infrastructure.rag_enhancements import build_rag_enhancements

        rewriter, reranker = build_rag_enhancements()
        if rewriter is None:
            print("[skip] 生产模型未配置，跳过增强组（当前为 fixed 适配器）")
            return [], []

    results: list[list[str]] = []
    ranks: list[tuple[str, int | None]] = []
    async with SessionFactory() as session:
        retriever = KnowledgeRetriever(session, rewriter=rewriter, reranker=reranker)
        for case in GOLDEN_SET:
            evidence = await retriever.search(case.query, limit=K)
            contents = [item.content for item in evidence]
            results.append(contents)
            ranks.append((case.query, first_hit_rank(case, contents)))
    return results, ranks


async def run_group(name: str, enhanced: bool) -> dict[str, float] | None:
    results, ranks = await collect_results(enhanced)
    if not results:
        return None
    metrics = evaluate_results(GOLDEN_SET, results, k=K)
    print(f"\n== {name} ==")
    for query, rank in ranks:
        mark = f"@{rank}" if rank is not None else "MISS"
        print(f"  {mark:<6} {query}")
    print(
        f"  hit@{K}={metrics['hit@k']:.2%}  MRR@{K}={metrics['mrr@k']:.3f}"
        f"  ({int(metrics['hits'])}/{int(metrics['cases'])})"
    )
    return metrics


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enhanced", action="store_true", help="附带 LLM 改写+精排组")
    args = parser.parse_args()

    async with SessionFactory() as session:
        published = await session.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.status == DocumentStatus.PUBLISHED)
        )
    if not published:
        print("知识库没有已发布文档，先运行摄入流程再评估。")
        return 1
    print(f"已发布文档：{published} | golden set：{len(GOLDEN_SET)} 条 | k={K}")

    baseline = await run_group("基线（关键词+向量融合）", enhanced=False)
    if args.enhanced:
        enhanced_metrics = await run_group("增强（查询改写+LLM 精排）", enhanced=True)
        if baseline and enhanced_metrics:
            print("\n== 增量 ==")
            print(
                f"  hit@{K}: {baseline['hit@k']:.2%} -> {enhanced_metrics['hit@k']:.2%}"
                f"  |  MRR@{K}: {baseline['mrr@k']:.3f} -> {enhanced_metrics['mrr@k']:.3f}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
