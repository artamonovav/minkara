from minkara import urls
from minkara.config import extract_code, generation_for

RULES = {
    "honda": {
        "brand_default": [
            {"generation": 1, "codes": ["GB1", "GB2", "GB3", "GB4"]},
            {"generation": 2, "codes": ["GB5", "GB6", "GB7", "GB8"]},
            {"generation": 3, "codes": ["GT1", "GT2", "GT6"]},
        ]
    }
}


def test_canonical_strips_tracking_and_fragment():
    url = "http://minkara.carview.co.jp/userid/1/car/2/3/note.aspx?ct=abc&_x_tr_sl=ja#title"
    assert urls.canonical(url) == "https://minkara.carview.co.jp/userid/1/car/2/3/note.aspx"


def test_canonical_keeps_page_and_drops_pn1():
    base = "https://minkara.carview.co.jp/car/honda/freed/note/"
    assert urls.canonical(base + "?pn=1") == base
    assert urls.canonical(base + "?pn=2") == base + "?pn=2"


def test_classify_note_and_listing():
    note = urls.classify("https://minkara.carview.co.jp/userid/10/car/20/30/note.aspx")
    assert note["kind"] == "note"
    assert (note["uid"], note["car"], note["note"]) == ("10", "20", "30")

    listing = urls.classify("https://minkara.carview.co.jp/car/honda/freed/note/?pn=3")
    assert listing["kind"] == "listing"
    assert listing["brand"] == "honda"
    assert listing["model"] == "freed"
    assert listing["pn"] == 3


def test_raw_relpath_layout():
    info = urls.classify("https://minkara.carview.co.jp/userid/10/car/20/30/note.aspx")
    assert urls.raw_relpath(info) == "userid/10/car/20/30/note.html"


def test_asset_relpath_keeps_cdn_structure():
    rel = urls.asset_relpath(
        "https://cdn.snsimg.carview.co.jp/minkara/note/000/006/379/447/6379447/p1.jpg?ct=x"
    )
    assert rel == "cdn.snsimg.carview.co.jp/minkara/note/000/006/379/447/6379447/p1.jpg"


def test_extract_code_and_generation():
    assert extract_code("6AA-GB7") == "GB7"
    assert extract_code("DBA-GB4") == "GB4"
    assert generation_for(RULES, "honda", "freed", "6AA-GB7") == 2
    assert generation_for(RULES, "honda", "freed", "DBA-GB4") == 1
    assert generation_for(RULES, "honda", "freed", "6AA-GT6") == 3
    assert generation_for(RULES, "honda", "freed", "XYZ-AA1") is None
