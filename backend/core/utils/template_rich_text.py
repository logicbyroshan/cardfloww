"""Helpers for handling rich-text export template content."""

import html
from html.parser import HTMLParser


class _TemplatePlainTextParser(HTMLParser):
    """Convert template rich HTML into plain text for export engines."""

    _BLOCK_TAGS = {
        'p', 'div', 'section', 'article', 'header', 'footer',
        'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote',
    }

    def __init__(self):
        super().__init__()
        self.parts = []

    def _append_newline(self):
        if not self.parts:
            return
        if self.parts[-1] != '\n':
            self.parts.append('\n')

    def handle_starttag(self, tag, attrs):
        tag_name = str(tag or '').lower()
        if tag_name == 'br':
            self._append_newline()
            return
        if tag_name in self._BLOCK_TAGS:
            self._append_newline()

    def handle_endtag(self, tag):
        tag_name = str(tag or '').lower()
        if tag_name in self._BLOCK_TAGS:
            self._append_newline()

    def handle_data(self, data):
        if data:
            self.parts.append(data)


def rich_text_to_plain_text(value: str) -> str:
    """Return plain-text representation of rich template HTML."""
    raw = str(value or '')
    if not raw:
        return ''

    if '<' not in raw and '&' not in raw:
        return raw.strip()

    parser = _TemplatePlainTextParser()
    parser.feed(raw)
    parser.close()

    text = ''.join(parser.parts)
    text = html.unescape(text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    lines = [ln.strip() for ln in text.split('\n')]
    compact_lines = []
    last_blank = False
    for line in lines:
        if not line:
            if not last_blank:
                compact_lines.append('')
            last_blank = True
            continue
        compact_lines.append(line)
        last_blank = False

    return '\n'.join(compact_lines).strip()
