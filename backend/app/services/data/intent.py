from __future__ import annotations

from backend.app.services.data.models import Evidence


def expand_query(query: str, products: list[str] | None = None) -> str:
    additions: list[str] = []
    product_set = set(products or [])
    normalized = query.lower()

    if (
        "宝可梦 朱／紫" in product_set
        and any(term in query for term in ("最初", "初始", "御三家", "三只"))
    ):
        additions.append("新叶喵 呆火鳄 润水鸭")

    if any(
        term in query
        for term in ("图鉴", "档案", "属性", "身高", "体重", "几只", "哪些灵兽")
    ):
        additions.append("图鉴 档案 属性 身高 体重")

    if any(term in query for term in ("版本", "更新", "维护", "公告", "停服")):
        additions.append("版本 更新 维护 公告")

    if any(term in query for term in ("礼包", "付费", "抽卡", "补偿", "商业化")):
        additions.append("礼包 抽卡 付费 补偿 水晶")

    if any(term in query for term in ("平台", "下载", "安装包", "品类定位")):
        additions.append("平台 下载 官网 品类 定位")

    if any(term.lower() in normalized for term in ("公会", "社交", "赛事", "pvp")):
        additions.append("公会 社交 赛事 PVP 对战")

    if "养成" in query and any(term in query for term in ("差异", "对比", "区别")):
        additions.append("养成 进化 升星 Mega 资质 努力值")

    values = [query, *additions]
    return " ".join(dict.fromkeys(value for value in values if value))


def section_boost(query: str, evidence: Evidence) -> float:
    section = evidence.section
    boost = 0.0
    social_terms = [
        term
        for term in ("公会", "社交", "赛事", "PVP")
        if term.lower() in query.lower()
    ]
    for term in social_terms:
        if term.lower() in evidence.title.lower():
            boost = max(boost, 1.05)
        elif term.lower() in evidence.text.lower():
            boost = max(boost, 0.25)
    if (
        any(term in query for term in ("图鉴", "基础档案"))
        and "图鉴" in section
    ):
        boost = max(boost, 0.95)
    if any(term in query for term in ("图鉴", "档案", "身高", "体重", "属性")):
        if "图鉴" in section:
            boost = max(boost, 0.16)
    if any(term in query for term in ("版本", "更新", "维护", "公告", "停服")):
        if any(term in section for term in ("资讯", "公告", "最新")):
            boost = max(boost, 0.08)
    if any(term in query for term in ("礼包", "付费", "抽卡", "补偿")):
        if any(term in section for term in ("礼包", "福利", "基础信息", "资讯")):
            boost = max(boost, 0.08)
    if any(term in query for term in ("平台", "下载", "安装包", "品类定位")):
        if any(term in section for term in ("下载", "基础信息")):
            boost = max(boost, 0.14)
    return boost
