"""存量回填：把库里已有的原文换成 LLM 摘要，content 列清空。

用法（在 backend/ 目录下，容器内或宿主机 venv 均可）：

    # 先看要处理多少条、样例长什么样（不改数据）
    PYTHONPATH=. ./venv/bin/python scripts/purge_originals.py --dry-run

    # 正式回填
    PYTHONPATH=. ./venv/bin/python scripts/purge_originals.py

    # 只处理一部分 / 出错时保留原文
    PYTHONPATH=. ./venv/bin/python scripts/purge_originals.py --limit 50 --keep-on-fail

规则
----
* 待处理：``content`` 非空，或 ``len(summary) > 150``（与线上判定阈值一致）
* 成功：``summary`` = LLM 摘要，``content`` = NULL
* 失败：默认保留原文并计入失败清单（``--keep-on-fail``，避免信息丢失）；
  加 ``--clear-on-fail`` 则强行清空 content（摘要缺失，慎用）
"""

import argparse
import asyncio
import sys
from typing import List, Tuple

from loguru import logger

from app.ai_pipeline.article_summarizer import (
    ORIGINAL_THRESHOLD,
    ArticleSummarizer,
    fold_content,
    is_original,
)
from app.core.config import get_settings
from app.database import SessionLocal
from app.models.models import Article


def _needs_fix(a: Article) -> bool:
    """有待处理：有原文要 LLM，或 content 需要归并进 summary。"""
    if a.content:
        return True
    return len((a.summary or "").strip()) > ORIGINAL_THRESHOLD


def _text(a: Article) -> str:
    parts = [p for p in ((a.summary or "").strip(), (a.content or "").strip()) if p]
    return "\n\n".join(parts)


async def run(dry_run: bool, limit: int | None, keep_on_fail: bool, clear_on_fail: bool) -> int:
    db = SessionLocal()
    summarizer = ArticleSummarizer()
    try:
        rows: List[Article] = db.query(Article).filter(Article.content.isnot(None)).all()
        rows += [
            a
            for a in db.query(Article)
            .filter(Article.content.is_(None))
            .filter(Article.summary.isnot(None))
            .all()
            if len((a.summary or "").strip()) > ORIGINAL_THRESHOLD
        ]
        rows = [a for a in rows if _needs_fix(a)]
        # 去重（两段查询可能重叠）
        seen = set()
        rows = [a for a in rows if not (a.id in seen or seen.add(a.id))]

        logger.info(f"待回填 {len(rows)} 条（content 非空 或 summary > {ORIGINAL_THRESHOLD} 字）")
        if limit:
            rows = rows[:limit]
            logger.info(f"--limit 生效，本次只处理 {len(rows)} 条")

        if dry_run:
            for a in rows[:10]:
                logger.info(
                    f"[dry-run] id={a.id} src={a.source_name} "
                    f"summary={len(a.summary or '')}字 content={len(a.content or '')}字 "
                    f"title={a.title[:40]}"
                )
            logger.info(f"[dry-run] 未修改任何数据，共 {len(rows)} 条待处理")
            return 0

        sem = asyncio.Semaphore(4)
        ok, failed, failed_rows = 0, 0, []

        async def _one(a: Article) -> None:
            nonlocal ok, failed

            # 合计不超过阈值：不调 LLM，content 并进 summary
            if len(_text(a)) <= ORIGINAL_THRESHOLD:
                if a.content:
                    merged = _text(a)
                    a.summary = merged
                    a.content = None
                ok += 1
                return

            async with sem:
                summary = await summarizer.summarize_text(a.title, _text(a))
            if summary:
                a.summary = summary
                a.content = None
                ok += 1
            else:
                failed += 1
                failed_rows.append((a.id, a.source_name, a.title[:50]))
                if clear_on_fail:
                    a.content = None

        await asyncio.gather(*(_one(a) for a in rows))
        db.commit()

        logger.info(f"回填完成：成功 {ok}，失败 {failed}")
        if failed:
            for rid, src, title in failed_rows:
                logger.error(f"  失败 id={rid} src={src} {title}")
            if not (keep_on_fail or clear_on_fail):
                logger.error(
                    "默认策略：失败的行保留原文（未清 content），可用 --clear-on-fail 强制清空"
                )
        return 0 if failed == 0 else 1
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="把存量原文换成 LLM 摘要")
    parser.add_argument("--dry-run", action="store_true", help="只报告，不改数据")
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 条")
    parser.add_argument("--keep-on-fail", action="store_true", help="失败保留原文（默认行为）")
    parser.add_argument("--clear-on-fail", action="store_true", help="失败也清空 content")
    args = parser.parse_args()

    if not get_settings().OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY 为空，无法回填")
        return 2

    try:
        return asyncio.run(
            run(args.dry_run, args.limit, args.keep_on_fail, args.clear_on_fail)
        )
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
