from backend.app.services.ingestion.crawlers import (
    CRAWLERS,
    HostRateLimiter,
    clean_html_text,
    crawl_snapshot_key,
    document_from_html,
)
from backend.app.services.ingestion import crawlers


def test_crawler_registry_covers_all_four_products():
    assert set(CRAWLERS) == {
        "donghuangji",
        "lqmc",
        "pkmbattle",
        "pokemon_sv",
    }
    assert {item.product for item in CRAWLERS.values()} == {
        "东煌纪",
        "乐趣萌宠",
        "战斗吧精灵",
        "宝可梦 朱／紫",
    }


def test_clean_html_removes_scripts_navigation_and_duplicate_lines():
    html = """
    <html><body>
      <nav>首页 登录</nav>
      <main>
        <h1>版本公告</h1>
        <script>alert(1)</script>
        <p>本次更新开放新地图。</p>
        <p>本次更新开放新地图。</p>
      </main>
    </body></html>
    """

    text = clean_html_text(html)

    assert "alert" not in text
    assert "首页 登录" not in text
    assert text.count("本次更新开放新地图。") == 1


def test_lqmc_document_id_is_stable_and_independent_of_page_title():
    first = document_from_html(
        product="乐趣萌宠",
        url="https://lqmc.net/features.html",
        html="<main><h1>旧标题</h1><p>玩法说明正文。</p></main>",
        section="玩法特色",
        doc_id="lqmc_features",
    )
    second = document_from_html(
        product="乐趣萌宠",
        url="https://lqmc.net/features.html",
        html="<main><h1>新标题</h1><p>玩法说明正文。</p></main>",
        section="玩法特色",
        doc_id="lqmc_features",
    )

    assert first.doc_id == second.doc_id == "lqmc_features"
    assert first.body == second.body
    assert first.title == "旧标题"
    assert second.title == "新标题"
    assert first.url.endswith("features.html")


def test_empty_crawled_body_is_rejected():
    try:
        document_from_html(
            product="乐趣萌宠",
            url="https://lqmc.net/empty.html",
            html="<main><script>only script</script></main>",
            section="官网资讯",
            doc_id="lqmc_empty",
        )
    except ValueError as error:
        assert "正文" in str(error)
    else:
        raise AssertionError("empty page should not produce a document")


def test_lqmc_sitemap_index_expands_child_sitemaps(monkeypatch):
    class Response:
        def __init__(self, text):
            self.text = text

    pages = {
        "https://lqmc.net/sitemap.xml": (
            "<sitemapindex>"
            "<sitemap><loc>https://www.lqmc.net/wp-sitemap-posts-post-1.xml</loc></sitemap>"
            "<sitemap><loc>https://www.lqmc.net/wp-sitemap-posts-page-1.xml</loc></sitemap>"
            "</sitemapindex>"
        ),
        "https://www.lqmc.net/wp-sitemap-posts-post-1.xml": (
            "<urlset>"
            "<url><loc>https://www.lqmc.net/10.html</loc></url>"
            "<url><loc>https://www.lqmc.net/11.html</loc></url>"
            "</urlset>"
        ),
        "https://www.lqmc.net/wp-sitemap-posts-page-1.xml": (
            "<urlset>"
            "<url><loc>https://www.lqmc.net/features.html</loc></url>"
            "</urlset>"
        ),
    }

    monkeypatch.setattr(
        crawlers,
        "_fetch",
        lambda _session, url: Response(pages[url]),
    )

    urls = crawlers._lqmc_urls(object())

    assert urls == [
        "https://www.lqmc.net/10.html",
        "https://www.lqmc.net/11.html",
        "https://www.lqmc.net/features.html",
    ]


def test_crawl_snapshot_key_is_content_versioned():
    key = crawl_snapshot_key(
        "crawler_lqmc",
        "abcdef1234567890",
        "lqmc_7",
        "html",
    )

    assert key == "snapshots/crawler_lqmc/abcdef1234567890/lqmc_7.html"


def test_rate_limiter_waits_between_same_host_requests():
    class Clock:
        now = 0.0

    sleeps = []
    clock = Clock()
    limiter = HostRateLimiter(
        1.0,
        clock=lambda: clock.now,
        sleep=lambda seconds: sleeps.append(seconds),
    )
    limiter.wait("https://example.test/a")
    clock.now = 0.25
    limiter.wait("https://example.test/b")
    limiter.wait("https://other.test/a")

    assert sleeps == [0.75]
