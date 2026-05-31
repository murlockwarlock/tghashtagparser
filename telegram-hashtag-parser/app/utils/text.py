import hashlib
import html
import re

from app.utils.html_utils import PostHTMLCleaner, fix_unclosed_html_tags

def clean_post_text(text: str, soft_promo_words: list[str]) -> str:
    if not text:
        return ""
    
    cleaner = PostHTMLCleaner()
    cleaner.feed(text)
    html_cleaned = cleaner.get_cleaned_html()
    
    lines = html_cleaned.split('\n')
    cleaned_lines = []
    
    trade_keywords = {"entry", "tp", "sl", "target", "buy", "sell", "long", "short", "stop"}
    
    for line in lines:
        lower_line = line.lower()
        
        has_promo = False
        promo_match = None
        
        if soft_promo_words:
            for word in soft_promo_words:
                match = re.search(rf"(?<![\wа-яё]){re.escape(word)}(?![\wа-яё])", lower_line)
                if match:
                    has_promo = True
                    # Keep the earliest match to truncate properly
                    if not promo_match or match.start() < promo_match.start():
                        promo_match = match
        
        if has_promo:
            has_trade = any(re.search(rf"(?<![\wа-яё]){kw}(?![\wа-яё])", lower_line) for kw in trade_keywords)
            if has_trade:
                # Truncate line before promo word
                line = line[:promo_match.start()]
                cleaned_lines.append(line)
                continue
            else:
                # Footer starts here: drop this line and all subsequent lines
                break
                
        cleaned_lines.append(line)
        
    res = '\n'.join(cleaned_lines)
    res = re.sub(r'\n{3,}', '\n\n', res)
    return fix_unclosed_html_tags(res.strip())


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def html_escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def trim(value: str, limit: int = 3000) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def parse_duration_minutes(text: str) -> int:
    text = text.lower().replace(" ", "")
    if text.isdigit():
        return int(text)
    
    total_minutes = 0
    matches = re.findall(r'(\d+(?:\.\d+)?)([hmчм])', text)
    if not matches:
        raise ValueError("Invalid duration format")
    for val, unit in matches:
        val = float(val)
        if unit in ('h', 'ч'):
            total_minutes += int(val * 60)
        elif unit in ('m', 'м'):
            total_minutes += int(val)
    if total_minutes == 0 and not matches:
        raise ValueError("Invalid duration format")
    return total_minutes
