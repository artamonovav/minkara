from minkara import quality


def test_good_translation():
    score, reasons = quality.score_translation(
        "オイル交換をしました。", "Заменил моторное масло."
    )
    assert score == 0
    assert reasons == []


def test_untranslated_is_bad():
    score, _ = quality.score_translation("オイル交換", "オイル交換")
    assert score >= 5
    assert quality.is_bad("オイル交換", "オイル交換")


def test_cjk_leftover_is_bad():
    score, reasons = quality.score_translation("整備手帳", "整備手帳について")
    assert score >= 5
    assert any("японский" in reason for reason in reasons)


def test_latin_product_name_allowed():
    score, _ = quality.score_translation(
        "PIRELLI(ピレリ) ICE ZERO 185/65R15",
        "PIRELLI ICE ZERO 185/65R15",
    )
    assert score == 0


def test_bad_term_variant_flagged():
    score, reasons = quality.score_translation(
        "オイル交換をしました。", "Сделал обмен масла."
    )
    assert score >= 2
    assert any("交換" in reason for reason in reasons)
