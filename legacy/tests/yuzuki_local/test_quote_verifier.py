from yuzuki_local.workers.quote_verifier import QuoteVerifier, normalize


def test_normalize_unifies_quotes_case_and_spaces():
    assert normalize("  “Kind”   Girl\n") == '"kind" girl'


def test_exact_and_curly_quote_match(context_text):
    v = QuoteVerifier(context_text, threshold=90, min_chars=15)
    check = v.check(['she is "kind" to her friends', "She plays the guitar every weekend"])
    assert check.valid and check.scores == (100.0, 100.0)


def test_fuzzy_match_tolerates_a_typo_but_not_invention(context_text):
    v = QuoteVerifier(context_text, threshold=90, min_chars=15)
    assert v.check(["She plays the guitar evry weekend"]).valid
    assert not v.check(["She hates guitars and never plays any music at all"]).valid


def test_short_quote_never_matches(context_text):
    assert QuoteVerifier(context_text, 90, 15).check(["student"]).scores == (0.0,)


def test_judge_no_data_needs_no_evidence(context_text):
    v = QuoteVerifier(context_text, 90, 15)
    assert v.judge([], no_data=True) == ((), None, ())


def test_judge_claim_without_quotes_is_invalid(context_text):
    assert QuoteVerifier(context_text, 90, 15).judge([" "], no_data=False)[1] is False


def test_judge_any_found_quote_is_enough(context_text):
    quotes, valid, scores = QuoteVerifier(context_text, 90, 15).judge(
        ["completely invented sentence about nothing", "She plays the guitar every weekend"], no_data=False)
    assert valid is True and scores[0] < 90 <= scores[1]
