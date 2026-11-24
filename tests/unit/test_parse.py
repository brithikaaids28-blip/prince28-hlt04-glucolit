from pathlib import Path

import pymupdf
import pytest

from glucolit.ingest.parse import (
    ParseError,
    clean_text,
    drop_repeated_lines,
    finish,
    headings_in,
    parse_file,
    parse_pdf_pymupdf,
    parse_pdf_pypdf,
    with_heading_paths,
)


def make_pdf(
    path: Path,
    text: str = "This is a sample research document with enough text for testing PDF extraction.",
) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), text)
    doc.save(path)
    doc.close()
    return path


def test_clean_text_normalizes_unicode():
    assert clean_text("ﬁle   test") == "file test"


def test_clean_text_removes_null_characters():
    assert clean_text("hello\x00world") == "helloworld"


def test_clean_text_joins_hyphenated_words():
    assert clean_text("treat-\nment") == "treatment"


def test_drop_repeated_lines():
    pages = [
        "Header\nContent one\nFooter",
        "Header\nContent two\nFooter",
        "Header\nContent three\nFooter",
        "Header\nContent four\nFooter",
    ]
    result = drop_repeated_lines(pages)
    assert all("Header" not in page and "Footer" not in page for page in result)


def test_drop_repeated_lines_short_document():
    pages = ["Page one", "Page two"]
    assert drop_repeated_lines(pages) == pages


def test_headings_in_finds_markdown_headings():
    found, _ = headings_in("# Main\n## Section")
    assert found == [(1, "Main"), (2, "Section")]


def test_headings_in_ignores_code_blocks():
    found, _ = headings_in("```python\n# Not a heading\n```\n# Real heading")
    assert found == [(1, "Real heading")]


def test_with_heading_paths():
    pages = with_heading_paths(["# Main\n## Section", "Some more content"])
    assert pages[0].page_no == 1
    assert pages[1].headings == ["Main", "Section"]


def test_finish_raises_for_empty_content():
    with pytest.raises(ParseError) as error:
        finish("plain", "text", "", ["", "   "])
    assert error.value.reason == "empty"


def test_finish_uses_first_heading_as_title():
    result = finish("plain", "text", "File name", ["# Research Title\nSome content"])
    assert result.title == "Research Title"


def test_parse_markdown_file(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("# Diabetes Research\nSome useful research content.", encoding="utf-8")
    result = parse_file(path)
    assert result.kind == "text"
    assert result.title == "Diabetes Research"


def test_parse_json_file(tmp_path):
    path = tmp_path / "sample.json"
    path.write_text('{"name": "diabetes"}', encoding="utf-8")
    result = parse_file(path)
    assert result.kind == "data"
    assert result.title == "sample"


def test_parse_html_file(tmp_path):
    path = tmp_path / "sample.html"
    path.write_text(
        "<html><head><title>Research</title></head><body>"
        "<article><h1>Diabetes Research</h1>"
        "<p>This is a sufficiently long research article with useful information.</p>"
        "</article></body></html>",
        encoding="utf-8",
    )
    result = parse_file(path)
    assert result.kind == "html"
    assert result.pages


def test_parse_unsupported_file(tmp_path):
    path = tmp_path / "sample.zip"
    path.write_text("test", encoding="utf-8")
    with pytest.raises(ParseError) as error:
        parse_file(path)
    assert error.value.reason == "unsupported_type"


def test_parse_pdf_with_pymupdf(tmp_path):
    path = make_pdf(tmp_path / "sample.pdf")
    result = parse_pdf_pymupdf(path)
    assert result.kind == "pdf"
    assert result.parser == "pymupdf"
    assert result.pages


def test_parse_pdf_with_pypdf(tmp_path):
    path = make_pdf(tmp_path / "sample.pdf")
    result = parse_pdf_pypdf(path)
    assert result.kind == "pdf"
    assert result.parser == "pypdf"
    assert result.pages


def test_parse_jats_xml_file(tmp_path):
    path = tmp_path / "article.xml"
    path.write_text(
        """<?xml version="1.0"?>
        <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
            <GetRecord>
                <record>
                    <metadata>
                        <article xmlns="https://jats.nlm.nih.gov/archiving/1.4/">
                            <front>
                                <article-meta>
                                    <title-group>
                                        <article-title>Diabetes Research in India</article-title>
                                    </title-group>
                                    <abstract>
                                        <p>This study examines diabetes in India.</p>
                                    </abstract>
                                </article-meta>
                            </front>
                            <body>
                                <sec>
                                    <title>Introduction</title>
                                    <p>Diabetes is a major public health concern.</p>
                                </sec>
                            </body>
                        </article>
                    </metadata>
                </record>
            </GetRecord>
        </OAI-PMH>
        """,
        encoding="utf-8",
    )

    result = parse_file(path)

    assert result.parser == "jats"
    assert result.kind == "xml"
    assert result.title == "Diabetes Research in India"
    assert "Introduction" in result.pages[0].text
    assert "public health concern" in result.pages[0].text
