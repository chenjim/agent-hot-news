"""标题归一化 —— 用于事件的确定性硬合并（方案 A）。

新闻事件标题完全相同却建成两个事件，是纯向量阈值判不出来的一类重复
（向量分数在"同事件"和"相关事件"上重叠）。归一化后的标题字符串相等
则是可确定性判定的强信号：同一条新闻的两版 LLM 标题不该只差标点、
空格或全半角。

归一化只做无损等价变换（NFKC + 去掉非中英文数字字符 + 小写），
不删词、不缩写、不做语义变换 —— 保证"归一化相等 ⇒ 大概率同一事件"，
不引入误并。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# 保留 CJK 统一表意（含扩展A、兼容区）与 ASCII 字母数字，其余全部剔除
_KEEP = re.compile(
    "[^"
    "\u4e00-\u9fff"  # CJK Unified
    "\u3400-\u4dbf"  # CJK Extension A
    "\uf900-\ufaff"  # CJK Compatibility
    "A-Za-z0-9"
    "]+"
)


def normalize_title(title: Optional[str]) -> str:
    """归一化标题，用于精确相等比对。

    空标题或纯符号标题返回空串，调用方必须跳过（空串相等无意义）。
    """
    if not title:
        return ""
    text = unicodedata.normalize("NFKC", str(title)).lower()
    return _KEEP.sub("", text)
