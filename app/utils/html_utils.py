import re
import html
from html.parser import HTMLParser

def fix_unclosed_html_tags(text: str) -> str:
    """Полностью перестраивает HTML-теги для корректной вложенности.
    Обрабатывает ВСЕ виды невалидного HTML.
    """
    allowed_tags = {'b', 'i', 's', 'code', 'pre', 'blockquote', 'tg-spoiler', 'u', 'strike', 'tg-emoji', 'span'}
    tag_pattern = re.compile(r'<(/?)([a-z1-6\-]+)([^>]*)>', re.IGNORECASE)

    segments = []
    last_end = 0
    for match in tag_pattern.finditer(text):
        tag_name = match.group(2).lower()
        if tag_name not in allowed_tags:
            continue
        if match.start() > last_end:
            segments.append(('text', text[last_end:match.start()]))
        is_closing = bool(match.group(1))
        segments.append(('close' if is_closing else 'open', tag_name, match.group(0)))
        last_end = match.end()
    if last_end < len(text):
        segments.append(('text', text[last_end:]))

    result = []
    stack = []

    for seg in segments:
        if seg[0] == 'text':
            result.append(seg[1])
        elif seg[0] == 'open':
            tag_name = seg[1]
            if any(t[0] == tag_name for t in stack):
                continue
            stack.append((tag_name, seg[2]))
            result.append(seg[2])
        elif seg[0] == 'close':
            tag_name = seg[1]
            idx = None
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag_name:
                    idx = i
                    break
            if idx is None:
                continue
            tags_to_reopen = []
            while len(stack) > idx + 1:
                t = stack.pop()
                result.append(f'</{t[0]}>')
                tags_to_reopen.append(t)
            stack.pop()
            result.append(f'</{tag_name}>')
            for t in reversed(tags_to_reopen):
                stack.append(t)
                result.append(t[1])

    while stack:
        t = stack.pop()
        result.append(f'</{t[0]}>')

    return ''.join(result)

def markdown_to_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<b>(.*?)</b>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<i>(.*?)</i>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<em>(.*?)</em>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<pre><code>(.*?)</code></pre>', r'```\1```', text, flags=re.DOTALL)
    text = re.sub(r'<code>(.*?)</code>', r'`\1`', text, flags=re.DOTALL)

    text = html.escape(text, quote=False)
    placeholders = {}

    def _placeholder(prefix, value):
        key = f"\x01{prefix}{len(placeholders)}\x01"
        placeholders[key] = value
        return key

    def save_escaped(match):
        return _placeholder("ESC", match.group(1))

    text = re.sub(r'\\([*_~`#\[\]()\\>!|-])', save_escaped, text)

    def save_code_block(match):
        code = match.group(1)
        code = re.sub(r'^[a-zA-Z0-9_+-]+\n', '', code)
        return _placeholder("CODEBLOCK", code)

    def save_inline_code(match):
        return _placeholder("INLINE", match.group(1))

    text = re.sub(r'```(.*?)```', save_code_block, text, flags=re.DOTALL)
    text = re.sub(r'`(.*?)`', save_inline_code, text)
    text = re.sub(r'^\s*[\*_-]{3,}\s*$', '———', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\*\s*$', '———', text, flags=re.MULTILINE)

    def _format_quote_content(content):
        content = re.sub(r'^\s*#{1,6}\s+(.*)', lambda m: '<b>' + m.group(1).replace('***', '').replace('**', '').replace('*', '') + '</b>', content, flags=re.MULTILINE)
        content = re.sub(r'^\s*[-*]\s+', '• ', content, flags=re.MULTILINE)
        return content

    def process_blockquotes(txt):
        lines = txt.split('\n')
        result = []
        quote_lines = []

        def flush_quote():
            if not quote_lines:
                return
            content = '\n'.join(quote_lines).strip()
            if content:
                content = _format_quote_content(content)
                result.append(f'<blockquote>{content}</blockquote>')
            quote_lines.clear()

        for line in lines:
            m = re.match(r'^\s*&gt;\s?(.*)', line)
            if m:
                quote_lines.append(m.group(1))
            else:
                flush_quote()
                result.append(line)
        flush_quote()
        return '\n'.join(result)

    text = process_blockquotes(text)
    text = re.sub(r'^\s*[-*]\s+', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*#{1,6}\s+(.*)', lambda m: '\n\n<b>' + m.group(1).replace('***', '').replace('**', '').replace('*', '') + '</b>\n', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*\*(?=[^<>]*\*\*\*)((?:(?!\n\n)[^<>])+?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'___((?:(?!\n\n)[^<>])+?)___', r'<b><i>\1</i></b>', text)
    text = re.sub(r'\*\*(?=[^<>]*\*\*)((?:(?!\n\n)[^<>])+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(?=[^<>]*__)((?:(?!\n\n)[^<>])+?)__', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\w)\*(?!\s)([^<>\n]+?)(?<!\s)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_(?!\s)([^<>\n]+?)(?<!\s)_(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'~~(?=[^<>\n]+~~)([^<>\n]+?)~~', r'<s>\1</s>', text)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'([^\n])\n(<b>)', r'\1\n\n\2', text)
    text = re.sub(r'([^\n])\n(•)', r'\1\n\n\2', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.replace('**', '').replace('__', '').replace('~~', '')
    text = text.replace('<b></b>', '').replace('<i></i>', '')
    text = re.sub(r'(?<![\w*])\*(?![\w*])', '', text)

    for key, value in placeholders.items():
        if "CODEBLOCK" in key:
            text = text.replace(key, f'<pre><code>{value}</code></pre>')
        elif "INLINE" in key:
            text = text.replace(key, f'<code>{value}</code>')
        else:
            text = text.replace(key, value)

    return fix_unclosed_html_tags(text.strip())

def remove_markdown(text: str) -> str:
    text = re.sub(r'#+\s+', '', text)
    text = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', r'\1', text)
    text = re.sub(r'\*(.*?)\*|_(.*?)_', r'\1', text)
    text = re.sub(r'~~(.*?)~~', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'\1', text)
    return text

def split_html_text(text: str, max_length: int = 4090) -> list[str]:
    if not text:
        return []
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    open_tags = []

    tag_re = re.compile(r'(</?[a-z1-6\-]+(?: [^>]+)?>)', re.IGNORECASE)
    parts = tag_re.split(text)

    def _suffix():
        return "".join([f"</{t[0]}>" for t in reversed(open_tags)])

    def _reopen():
        return "".join([t[1] for t in open_tags])

    def _close_size():
        return sum(len(t[0]) + 3 for t in open_tags)

    for part in parts:
        if not part:
            continue
        if part.startswith('<'):
            tag_match = re.match(r'<(/?)([a-z1-6\-]+)', part, re.IGNORECASE)
            if tag_match:
                is_closing = bool(tag_match.group(1))
                tag_name = tag_match.group(2).lower()
                if is_closing:
                    if open_tags and open_tags[-1][0] == tag_name:
                        open_tags.pop()
                elif tag_name not in ['br', 'hr', 'img']:
                    open_tags.append((tag_name, part))

            suffix = _suffix()
            if len(current_chunk) + len(part) + len(suffix) > max_length:
                if current_chunk.strip():
                    chunks.append(current_chunk + suffix)
                current_chunk = _reopen()

            current_chunk += part
        else:
            while len(current_chunk) + len(part) + _close_size() > max_length:
                remaining_space = max_length - len(current_chunk) - _close_size()

                if remaining_space <= 10:
                    suffix = _suffix()
                    if current_chunk.strip():
                        chunks.append(current_chunk + suffix)
                    current_chunk = _reopen()
                    remaining_space = max_length - len(current_chunk) - _close_size()

                split_at = remaining_space

                for separator in ('\n\n', '. ', '! ', '? ', '\n'):
                    found_at = part.rfind(separator, 0, remaining_space)
                    if found_at != -1 and found_at > (remaining_space // 3):
                        split_at = found_at + len(separator.rstrip())
                        break
                else:
                    split_at = part.rfind(' ', 0, remaining_space)
                    if split_at == -1:
                        split_at = remaining_space

                content = part[:split_at]
                suffix = _suffix()

                if (current_chunk + content).strip():
                    chunks.append(current_chunk + content + suffix)

                current_chunk = _reopen()
                part = part[split_at:].lstrip()

            current_chunk += part

    if current_chunk.strip():
        clean_chunk = re.sub(r'(<[a-z1-6\-][^>]*>)+$', '', current_chunk)
        if clean_chunk.strip():
            suffix = _suffix()
            final_c = clean_chunk + suffix
            if re.sub(r'<[^>]+>', '', final_c).strip():
                chunks.append(final_c)

    return [fix_unclosed_html_tags(c) for c in chunks if re.sub(r'<[^>]+>', '', c).strip()]


class PostHTMLCleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.result = []
        self.tag_map = {
            'emoji': 'tg-emoji',
            'spoiler': 'tg-spoiler',
            'strong': 'b',
            'em': 'i',
            'ins': 'u',
            'strike': 's',
            'del': 's'
        }
        self.allowed_tags = {
            'b', 'i', 'u', 's', 'code', 'pre', 'blockquote', 'tg-spoiler', 'tg-emoji', 'span'
        }
        self.ignore_tag_stack = []

    def handle_starttag(self, tag, attrs):
        lower_tag = tag.lower()
        mapped_tag = self.tag_map.get(lower_tag, lower_tag)

        if mapped_tag not in self.allowed_tags:
            self.ignore_tag_stack.append(lower_tag)
            return

        new_attrs = []
        for k, v in attrs:
            if mapped_tag == 'tg-emoji' and k == 'id':
                k = 'emoji-id'
            new_attrs.append((k, v))

        attr_str = "".join([f' {k}="{html.escape(v, quote=True)}"' if v is not None else f' {k}' for k, v in new_attrs])
        self.result.append(f"<{mapped_tag}{attr_str}>")

    def handle_endtag(self, tag):
        lower_tag = tag.lower()
        if self.ignore_tag_stack and self.ignore_tag_stack[-1] == lower_tag:
            self.ignore_tag_stack.pop()
            return
            
        mapped_tag = self.tag_map.get(lower_tag, lower_tag)
        if mapped_tag in self.allowed_tags:
            self.result.append(f"</{mapped_tag}>")

    def handle_data(self, data):
        text = re.sub(r'https?://[^\s]+', '', data)
        text = re.sub(r'(?i)t\.me/[^\s]+', '', text)
        text = re.sub(r'(?i)tg://[^\s]+', '', text)
        text = re.sub(r'@[a-zA-Z0-9_]+', '', text)
        self.result.append(text)

    def handle_entityref(self, name):
        self.result.append(f"&{name};")
        
    def handle_charref(self, name):
        self.result.append(f"&#{name};")

    def get_cleaned_html(self):
        return "".join(self.result)
