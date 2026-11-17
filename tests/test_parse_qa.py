from minkara import parse

QA_LISTING = """
<ul class="question-list">
  <li class="question-list__list">
    <h3 class="question-list__list__head__title">
      <a href="/car/honda/freed/qa/unit224980/">カウルトップの変形</a>
    </h3>
    <p class="question-list__list__head__answer">28</p>
    <p class="question-list__list__cat-name">[トラブル・故障]</p>
    <p class="question-list__list__content__text">本文 вопроса</p>
    <p class="question-list__list__content__data">2026年11月2日</p>
    <p class="question-list__list__content__name">
      <a href="/userid/1/profile/">Автор</a>
    </p>
  </li>
</ul>
"""

QA_UNIT = """
<div class="q-list">
  <div class="qa2 question clearfix">
    <h2 class="ttl">カウルトップの変形</h2>
    <span class="name"><a href="/userid/1/profile/">Автор</a></span>
    <span class="date">2025/10/06 23:30</span>
  </div>
  <div class="text">質問の本文<br/>詳細</div>
</div>
<ul class="a-list2">
  <li>
    <div class="qa2 answer2 clearfix">
      <span class="name"><a href="/userid/2/profile/">Отвечающий</a></span>
      <span class="date">2026/11/02 00:00</span>
    </div>
    <div class="text">回答です<br/>参考</div>
  </li>
</ul>
"""

MODEL = """
<h1>ホンダ フリード</h1>
<meta name="description" content="フリードの説明">
<a href="/car/honda/freed/note/">整備手帳</a>
<a href="/car/honda/freed/review/">クルマレビュー</a>
"""


def test_parse_qa_listing():
    items = parse.parse_qa_listing(QA_LISTING)
    assert len(items) == 1
    assert items[0]["url"] == "/car/honda/freed/qa/unit224980/"
    assert items[0]["answers"] == 28
    assert items[0]["category"] == "トラブル・故障"


def test_parse_qa_unit():
    qa = parse.parse_qa(QA_UNIT)
    assert qa["title"] == "カウルトップの変形"
    assert "詳細" in qa["question"]
    assert len(qa["answers"]) == 1
    assert qa["answers"][0]["author"] == "Отвечающий"
    assert "参考" in qa["answers"][0]["text"]


def test_parse_model():
    model = parse.parse_model(MODEL)
    assert model["title"] == "ホンダ フリード"
    assert "フリード" in model["description"]
    assert model["links"]["note"] == "/car/honda/freed/note/"


def test_qa_text_units():
    qa = parse.parse_qa(QA_UNIT)
    units = parse.extract_text_units(qa, "qa")
    kinds = {(unit["kind"], unit["idx"]) for unit in units}
    assert ("title", 0) in kinds
    assert ("qa", 1) in kinds
    assert ("qa", 2) in kinds
