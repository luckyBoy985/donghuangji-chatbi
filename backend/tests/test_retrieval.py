from dataclasses import replace
import pickle
from pathlib import Path

import numpy as np

from backend.app.services.data.models import Evidence
from backend.app.services.data.intent import expand_query, section_boost
from backend.app.services.data.repository import DataRepository
from backend.app.services.data.retrieval import (
    RetrievalEngine,
    diversify_results,
    filter_evidence,
    rrf_fuse,
)


def test_rrf_prefers_chunk_ranked_by_both_lists():
    lexical = [
        Evidence("a", "灵兽", "东煌纪", "产品资料", 1.0),
        Evidence("b", "版本", "东煌纪", "官方资讯", 0.8),
    ]
    dense = [
        Evidence("c", "地图", "乐趣萌宠", "官网", 0.9),
        Evidence("a", "灵兽", "东煌纪", "产品资料", 0.7),
    ]

    fused = rrf_fuse([lexical, dense], k=60)

    assert fused[0].chunk_id == "a"
    assert fused[0].score > fused[1].score


def test_product_and_section_filters_are_applied_together():
    hits = [
        Evidence("a", "灵兽", "东煌纪", "产品资料", 1.0),
        Evidence("b", "灵兽", "东煌纪", "官方资讯", 1.0),
        Evidence("c", "萌宠", "乐趣萌宠", "产品资料", 1.0),
    ]

    filtered = filter_evidence(hits, ["东煌纪"], ["产品资料"])

    assert [hit.chunk_id for hit in filtered] == ["a"]


def test_rrf_merges_metadata_from_first_seen_evidence():
    lexical = [
        replace(
            Evidence("a", "灵兽", "东煌纪", "产品资料", 1.0),
            doc_id="doc-a",
            title="灵兽系统说明",
        )
    ]
    dense = [Evidence("a", "灵兽", "东煌纪", "产品资料", 0.9)]

    fused = rrf_fuse([lexical, dense], k=60)

    assert fused[0].doc_id == "doc-a"


def test_cosine_similarity_returns_zero_for_empty_vector():
    from backend.app.services.data.retrieval import cosine_scores

    matrix = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    assert cosine_scores(matrix, np.zeros(2, dtype=np.float32)).tolist() == [0.0, 0.0]


def test_query_expands_initial_pokemon_names_for_catalog_question():
    expanded = expand_query("宝可梦朱紫最初的三只宝可梦", ["宝可梦 朱／紫"])

    assert "新叶喵" in expanded
    assert "呆火鳄" in expanded
    assert "润水鸭" in expanded


def test_section_boost_rewards_catalog_section_for_catalog_question():
    catalog = Evidence("a", "属性", "东煌纪", "灵兽图鉴", 0.0)
    news = Evidence("b", "属性活动", "东煌纪", "官方资讯", 0.0)

    assert section_boost("灵兽基础档案属性", catalog) > section_boost(
        "灵兽基础档案属性", news
    )


def test_explicit_catalog_scale_question_strongly_prefers_catalog_documents():
    catalog = Evidence("a", "属性", "东煌纪", "灵兽图鉴", 0.0)

    assert section_boost("图鉴规模差距", catalog) >= 0.5
    assert section_boost("灵兽属性和基础档案", catalog) >= 0.5


def test_social_query_prioritizes_pages_whose_title_names_the_feature():
    titled = Evidence(
        "a",
        "普通内容",
        "东煌纪",
        "官方资讯",
        0.0,
        doc_id="a",
        title="新公会战玩法介绍",
    )
    body_only = Evidence(
        "b",
        "提到公会但不具体",
        "东煌纪",
        "官方资讯",
        0.0,
        doc_id="b",
        title="版本公告",
    )

    assert section_boost("公会和社交玩法资料", titled) >= 1.0
    assert section_boost("公会和社交玩法资料", titled) > section_boost(
        "公会和社交玩法资料", body_only
    )


def test_multi_product_results_interleave_selected_products():
    candidates = [
        Evidence("a1", "A1", "东煌纪", "图鉴", 1.0, doc_id="a1"),
        Evidence("a2", "A2", "东煌纪", "图鉴", 0.9, doc_id="a2"),
        Evidence("b1", "B1", "宝可梦 朱／紫", "图鉴", 0.8, doc_id="b1"),
        Evidence("b2", "B2", "宝可梦 朱／紫", "图鉴", 0.7, doc_id="b2"),
    ]

    selected = diversify_results(candidates, 4, ["东煌纪", "宝可梦 朱／紫"])

    assert [item.chunk_id for item in selected] == ["a1", "b1", "a2", "b2"]


def test_multi_product_candidates_do_not_let_large_scope_hide_small_scope():
    repository = DataRepository(Path("unused.pkl"))
    repository.evidence = [
        Evidence(
            f"battle-{index}",
            "图鉴 属性",
            "战斗吧精灵",
            "资讯",
            0.0,
            doc_id=f"battle-{index}",
        )
        for index in range(60)
    ]
    repository.evidence.append(
        Evidence(
            "east-hero",
            "属性和身高体重",
            "东煌纪",
            "灵兽图鉴",
            0.0,
            doc_id="east-hero",
        )
    )
    repository.dense = np.tile(
        np.array([1.0, 0.0], dtype=np.float32),
        (len(repository.evidence), 1),
    )
    repository.dense[-1] = np.array([0.0, 1.0], dtype=np.float32)

    class FixedEmbedder:
        def encode_query(self, _query):
            return np.array([1.0, 0.0], dtype=np.float32)

    class ZeroReranker:
        def score(self, _query, passages):
            return [0.0 for _ in passages]

    engine = RetrievalEngine(repository, FixedEmbedder(), ZeroReranker())
    results = engine.search(
        "图鉴规模和属性档案",
        products=["东煌纪", "战斗吧精灵"],
        limit=5,
    )

    assert "east-hero" in [item.chunk_id for item in results]


def test_section_boost_applies_before_candidate_truncation():
    repository = DataRepository(Path("unused.pkl"))
    repository.evidence = [
        Evidence(
            f"news-{index}",
            "图鉴 属性 身高 体重",
            "东煌纪",
            "官方资讯",
            0.0,
            doc_id=f"news-{index}",
        )
        for index in range(50)
    ]
    repository.evidence.append(
        Evidence(
            "hero",
            "属性 身高 体重",
            "东煌纪",
            "灵兽图鉴",
            0.0,
            doc_id="hero",
        )
    )
    repository.dense = np.ones((51, 2), dtype=np.float32)

    class FixedEmbedder:
        def encode_query(self, _query):
            return np.array([1.0, 0.0], dtype=np.float32)

    class OptimisticReranker:
        def score(self, _query, passages):
            return [1.0 for _ in passages]

    engine = RetrievalEngine(repository, FixedEmbedder(), OptimisticReranker())
    results = engine.search(
        "灵兽属性和基础档案",
        products=["东煌纪"],
        limit=5,
    )

    assert results[0].chunk_id == "hero"


def test_repository_switches_to_platform_index_and_engine_rebuilds_bm25(
    tmp_path,
):
    base_path = tmp_path / "base.pkl"
    platform_path = tmp_path / "platform.pkl"

    def write_index(path, chunk_id, text):
        with path.open("wb") as handle:
            pickle.dump(
                {
                    "chunks": [
                        {
                            "chunk_id": chunk_id,
                            "doc_id": chunk_id,
                            "product": "东煌纪",
                            "source_type": "internal",
                            "section": "产品资料",
                            "title": text,
                            "url": "",
                            "published_at": "",
                            "text": text,
                        }
                    ],
                    "dense": np.ones((1, 1024), dtype=np.float32),
                },
                handle,
            )

    write_index(base_path, "old", "旧词正文")
    repository = DataRepository(base_path, platform_path)
    repository.load()

    class FixedEmbedder:
        def encode_query(self, _query):
            return np.ones(1024, dtype=np.float32)

    class ZeroReranker:
        def score(self, _query, passages):
            return [0.0 for _ in passages]

    engine = RetrievalEngine(repository, FixedEmbedder(), ZeroReranker())
    assert engine.search("旧词", limit=1)[0].chunk_id == "old"

    write_index(platform_path, "new", "新词正文")

    assert engine.search("新词", limit=1)[0].chunk_id == "new"
    assert [item.chunk_id for item in repository.evidence] == ["new"]
