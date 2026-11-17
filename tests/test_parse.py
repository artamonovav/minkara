from minkara import parse

LISTING = """
<ul>
  <li class="item">
    <a id="_ctl0_CPH1_UnitList_rList__ctl1_HL_Image"
       href="/userid/1/car/2/3/note.aspx">
      <ol class="figure4"><li><img src="https://cdn.example/p1mm.jpg"></li></ol>
    </a>
    <div class="textarea">
      <h2 class="article-title"><a href="/userid/1/car/2/3/note.aspx">Заголовок</a></h2>
      <p class="lead">Лид заметки</p>
    </div>
    <div class="bottominformation">
      <span class="date">2026年1月2日</span>
      <span class="username"><a href="/userid/1/profile/">Автор</a></span>
    </div>
    <ul class="sharevalue">
      <li class="like"><span class="value">3</span></li>
      <li class="comment"><span class="value">2</span></li>
    </ul>
    <div class="stars">
      <span class="cmn_icon_difficult"></span><span class="cmn_icon_difficult"></span>
    </div>
  </li>
</ul>
"""

NOTE = """
<h1 class="contentsTitle">フリードの整備</h1>
<p class="user-article-header__date">作業日：2021年5月19日</p>
<ul class="article-category-contents"><li><a href="/note/?bi=4">外装</a></li></ul>
<a id="_ctl0_CPH2_HL_UserCar" href="/userid/1/car/2/profile.aspx">моя машина</a>
<a id="_ctl0_CPH2_HL_UserCarTitle" href="/car/honda/freed/">ホンダ フリード</a>
<table>
  <tr><th>作業時間</th><td>30分以内</td></tr>
  <tr><th>難易度</th><td>初級</td></tr>
</table>
<div class="galleryTitle">1</div>
<div class="galleryPhoto"><a href="/x/1/note.aspx"><img src="https://cdn.example/p1.jpg"></a></div>
<div class="galleryMemo">オイル交換<br/>フィルター交換</div>
<div class="galleryTitle">2</div>
<div class="galleryPhoto"><a href="/x/2/note.aspx"><img src="https://cdn.example/p2.jpg"></a></div>
<div class="galleryMemo">エアフィルター交換</div>
<td>
  <div class="commentTitle"><a href="/userid/9/profile/">Вася</a></div>
  <div class="commentDate">2026年1月1日</div>
  <div class="commentArea half">ありがとう<br/>参考になりました</div>
</td>
<span id="txtLikeCount_LikeCommentClipForContentHeader">5</span>
"""

PROFILE = """
<h2 class="car_title">Моя машина</h2>
<table>
  <tr><th>グレード</th><td>ハイブリッド G</td></tr>
  <tr><th>型式</th><td>6AA-GB7</td></tr>
</table>
"""


def test_parse_listing():
    items = parse.parse_listing(LISTING)
    assert len(items) == 1
    item = items[0]
    assert item["url"] == "/userid/1/car/2/3/note.aspx"
    assert item["title"] == "Заголовок"
    assert item["likes"] == 3
    assert item["comments"] == 2
    assert item["difficulty"] == 2


def test_parse_listing_end_marker():
    assert parse.listing_has_items(LISTING)
    assert not parse.listing_has_items("<div>featured only</div>")


def test_parse_note():
    note = parse.parse_note(NOTE, "https://example/note.aspx")
    assert note["title"] == "フリードの整備"
    assert note["date"] == "2021年5月19日"
    assert note["work_time"] == "30分以内"
    assert note["difficulty"] == "初級"
    assert note["car_model"] == "ホンダ フリード"
    assert note["likes"] == 5
    assert len(note["gallery"]) == 2
    assert note["gallery"][0]["memo"] == "オイル交換\nフィルター交換"
    assert note["gallery"][1]["image"] == "https://cdn.example/p2.jpg"
    assert note["comments"][0]["author"] == "Вася"
    assert "参考" in note["comments"][0]["text"]


def test_parse_profile():
    profile = parse.parse_profile(PROFILE)
    assert profile["code"] == "6AA-GB7"
    assert profile["grade"] == "ハイブリッド G"


def test_extract_text_units_note():
    note = parse.parse_note(NOTE)
    units = parse.extract_text_units(note, "note")
    kinds = {(u["kind"], u["idx"]) for u in units}
    assert ("title", 0) in kinds
    assert ("memo", 1) in kinds
    assert ("memo", 2) in kinds
    assert ("comment", 1) in kinds
