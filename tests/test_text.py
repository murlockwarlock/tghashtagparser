from app.utils.text import clean_post_text
from app.utils.html_utils import fix_unclosed_html_tags

def test_clean_post_text_removes_links_and_promo():
    text = 'Check out my channel <a href="https://t.me/some_channel">Here</a> and @my_username\nSome VIP PROMO'
    soft = ['vip', 'promo']
    res = clean_post_text(text, soft)
    assert 'Check out my channel Here and' in res
    assert 'VIP PROMO' not in res
    assert '@my_username' not in res

def test_clean_post_text_keeps_trade_data_with_promo():
    text = "#SOLUSDT LONG Entry: 100 TP: 120 SL: 90 VIP"
    soft = ['vip']
    res = clean_post_text(text, soft)
    assert 'Entry: 100 TP: 120 SL: 90' in res
    assert 'VIP' not in res
    
    text2 = "Some random text\nJoin my VIP channel"
    res2 = clean_post_text(text2, soft)
    assert 'Some random text' in res2
    assert 'Join my VIP' not in res2

def test_fix_unclosed_html_tags():
    text = "<b>bold <i>italic"
    fixed = fix_unclosed_html_tags(text)
    assert fixed == "<b>bold <i>italic</i></b>"
