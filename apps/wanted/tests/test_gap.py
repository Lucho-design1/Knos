"""A recorded card's opening and closing lines (signals.gap), on synthetic cards: the model's city beside Qloo's, /proof/'s
number from the published table, what would flip the verdict, and each rejected option with its rule's code."""
from knos_wanted import signals


def card(**kw):
    return {"idea": "a synthetic idea nobody recorded", "decision": {"verdict": "REFUSE"}, "matches": [], "cities": [], **kw}


def test_the_sentence_names_both_cities_and_the_number_links_to_proof():
    g = signals.gap(card(model_alone={"city": "Austin, Texas"}, cities=[{"name": "Bend"}, {"name": "Tucson"}]))
    assert g["sentence"] == "Model alone says Austin, Texas. Qloo says Bend."
    h = g["headline"]
    assert h["href"].endswith("/Knos/proof/") and f"{h['n']} of {h['of']}" in h["said"] and h["of"] > 0


def test_no_city_from_qloo_is_said_so_and_no_model_answer_means_no_sentence():
    assert signals.gap(card(model_alone={"city": "Miami, Florida"}))["sentence"] == "Model alone says Miami, Florida. Qloo names no city."
    assert "sentence" not in signals.gap(card())


def test_every_card_has_a_flip_line_and_rejected_options_with_codes():
    g = signals.gap(card(cities=[{"name": "Bend"}], matches=[{"name": "Leader Co"}, {"name": "Other Co"}], leader={"name": "Leader Co"}))
    assert g["flip"]["said"].startswith("What would flip this verdict:")
    assert [(o["name"], o["code"]) for o in g["rejected"]] == [("Bend", "NO_MAP"), ("Other Co", "LESS_RELEVANT")]
    assert all(o["why"] == signals.CODES[o["code"]] for o in g["rejected"])


def test_a_recording_without_evidence_says_what_decided_it():
    g = signals.flip({"idea": "x", "decision": {"verdict": "REFUSE"}})
    assert g["from"] == "reason" and "Qloo matched none" in g["said"]
