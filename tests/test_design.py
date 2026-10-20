"""Report design system: sidebar with an index, bento grid, embedded fonts and interactive tables."""
import _report_styles as est


def test_page_with_index_sources_and_search():
    body = (est.section("Summary", "<p>x</p>") + est.two_col(est.section("One", "a"), est.section("Two", "b"))
            + est.section("Summary", "<p>y</p>", width=4))
    html = est.page("Report", "Test", est.meta([("Story", "US-001")]), body)
    assert 'class="side"' in html and 'id="nav"' in html and 'id="search"' in html
    assert html.count('data-nav="Summary"') == 2 and 'id="s-summary"' in html and 'id="s-summary-2"' in html  # unique ids
    assert "grid-column:span 4" in html
    assert "@font-face" in html and "font/woff2;base64," in html  # Saira, Inter and JetBrains Mono embedded: looks the same without internet
    assert "https://" not in html.split("<body>")[0]  # nothing is loaded from the internet


def test_indicators_with_progress_sparkline_and_status_with_text():
    k = est.kpi_tiles([("Passed", 14, "ok", "78%", "", {"pct": 78}), ("Load", "1.2 s", "", "", "clock", {"series": [3, 5, 2, 6]}),
                       ("Failed", 3, "bad")])
    assert 'style="width:78%"' in k and "<svg" in k and "✕ Critical" in k and "✓ OK" in k


def test_new_charts():
    assert "stroke-dasharray" in est.gauge(82, "score")
    assert "linearGradient" in est.column_chart([("A", 3), ("B", 5)])
    assert est.sparkline([1]) == ""
    panel = est.donut_panel([(3, est.OK, "OK"), (1, est.CRITICAL, "Bad")], 75, "ok")
    assert 'class="p"' in panel and "75%" in panel


def test_relative_absolute_and_missing_evidence(tmp_path):
    import generate_report
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "tc-001.png").write_bytes(b"x")
    assert est.resolve_evidence("evidence/tc-001.png", tmp_path) == ("evidence/tc-001.png", True)
    assert est.resolve_evidence(str(tmp_path / "evidence" / "tc-001.png"), tmp_path) == ("evidence/tc-001.png", True)
    assert est.resolve_evidence("evidence/no.png", tmp_path)[1] is False
    html = generate_report.build_html({"cases": [
        {"id": "TC-001", "title": "a", "status": "Passed", "evidence": "evidence/tc-001.png"},
        {"id": "TC-002", "title": "b", "status": "Failed", "evidence": "evidence/no.png"}]}, tmp_path)
    assert 'class="lb thumb s" href="evidence/tc-001.png"' in html and "! Evidence not found" in html
    assert "id='lb'" in html or "lb.id='lb'" in html  # the viewer is shared by every report
