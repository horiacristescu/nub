"""
Unit tests for text format strategy.
"""

from pathlib import Path

from nub.formats.text import TextStrategy
from nub.formats.base import registry


FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


class TestTextStrategy:
    def setup_method(self):
        self.strategy = TextStrategy()

    def test_name(self):
        assert self.strategy.name == "text"

    def test_extensions(self):
        assert ".txt" in self.strategy.extensions
        assert ".log" in self.strategy.extensions

    def test_parse_creates_sections(self):
        content = "line one\nline two\nline three"
        root = self.strategy.parse(content)

        # One section containing 3 lines
        assert root.type == "document"
        assert len(root.children) == 1
        section = root.children[0]
        assert section.type == "section"
        assert len(section.children) == 3

    def test_parse_lines_have_content(self):
        content = "first\nsecond\nthird"
        root = self.strategy.parse(content)

        section = root.children[0]
        assert section.children[0].content == "first"
        assert section.children[1].content == "second"
        assert section.children[2].content == "third"

    def test_parse_lines_are_named(self):
        content = "first\nsecond"
        root = self.strategy.parse(content)

        section = root.children[0]
        assert section.children[0].name == "L1"
        assert section.children[1].name == "L2"

    def test_parse_empty(self):
        root = self.strategy.parse("")
        assert root.type == "document"
        assert len(root.children) == 0

    def test_parse_single_line(self):
        root = self.strategy.parse("only one line")
        assert len(root.children) == 1
        section = root.children[0]
        assert len(section.children) == 1
        assert section.children[0].content == "only one line"

    def test_parse_blank_lines_create_sections(self):
        content = "line one\n\nline three"
        root = self.strategy.parse(content)

        # Two sections separated by blank line
        assert len(root.children) == 2
        assert root.children[0].children[0].content == "line one"
        assert root.children[1].children[0].content == "line three"

    def test_rank_section_higher_than_line(self):
        content = "a\n\nb"
        root = self.strategy.parse(content)

        section = root.children[0]
        line = section.children[0]

        section_score = self.strategy.rank(section)
        line_score = self.strategy.rank(line)

        assert section_score > line_score

    def test_parse_fixture_sample(self):
        content = (FIXTURES / "sample.txt").read_text()
        root = self.strategy.parse(content)

        # One section with 7 lines (no blank lines in file)
        assert len(root.children) == 1
        section = root.children[0]
        assert len(section.children) == 7
        assert "First line" in section.children[0].content
        assert "final line" in section.children[6].content

    def test_parse_fixture_unicode(self):
        content = (FIXTURES / "unicode.txt").read_text()
        root = self.strategy.parse(content)

        # One section with 5 lines
        assert len(root.children) == 1
        section = root.children[0]
        assert len(section.children) == 5
        assert "世界" in section.children[0].content
        assert "🎉" in section.children[3].content


class TestTextRegistry:
    def test_text_registered(self):
        strategy = registry.get_by_name("text")
        assert strategy is not None
        assert strategy.name == "text"

    def test_txt_extension_registered(self):
        strategy = registry.get_by_extension(".txt")
        assert strategy is not None
        assert strategy.name == "text"

    def test_log_extension_registered(self):
        strategy = registry.get_by_extension(".log")
        assert strategy is not None
        assert strategy.name == "text"
