from exec_assistant import checkins
from exec_assistant.llm import LLM
from tests.conftest import FakeClient


def scripted(answers):
    it = iter(answers)
    asked = []

    def ask(q):
        asked.append(q)
        return next(it)
    return ask, asked


def test_morning_interactive_with_mocked_llm(store, mock_llm, fake_client):
    ask, asked = scripted(["Ship pricing", "Hire EM", "Board deck", "7", "3", "legal review"])
    ctx = checkins.morning_context(store, "2026-10-05")
    answers = checkins.ask_morning(ctx, "2026-10-05", ask=ask, out=lambda *_: None)
    res = checkins.run_morning(store, mock_llm, answers, "2026-10-05", ctx=ctx)
    assert res["response"] == "Mocked Claude reply."
    assert [p["text"] for p in store.get_priorities("2026-10-05")] == ["Ship pricing", "Hire EM", "Board deck"]
    saved = store.get_checkin("2026-10-05", "morning")
    assert saved["energy"] == 7 and saved["meetings"] == 3 and saved["data"]["blockers"] == "legal review"
    call = fake_client.messages.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    assert "Ship pricing" in call["messages"][0]["content"]


def test_morning_uses_yesterdays_review_and_carries_over(store, dry_llm):
    checkins.run_morning(store, dry_llm, {"priorities": ["A", "B"], "energy": 6}, "2026-10-01")
    checkins.run_evening(store, dry_llm, {"completed": "y,n", "didnt_go_well": "too many meetings",
                                          "energy": 5, "mood": 6}, "2026-10-01")
    ctx = checkins.morning_context(store, "2026-10-02")
    assert ctx["prev_date"] == "2026-10-01" and ctx["unfinished"] == ["B"]
    assert "meeting" in ctx["prev_suggestion"].lower()
    ask, asked = scripted(["", "C", "", "8", "1", ""])  # accept carry-over, add C
    answers = checkins.ask_morning(ctx, "2026-10-02", ask=ask, out=lambda *_: None)
    assert answers["priorities"] == ["B", "C"]
    assert any("Carry these over" in q for q in asked)
    res = checkins.run_morning(store, dry_llm, answers, "2026-10-02", ctx=ctx)
    assert "Carried over: B" in res["response"]


def test_evening_scripted_stores_structured_data(store, mock_llm):
    checkins.run_morning(store, mock_llm, {"priorities": "A; B; C", "energy": 7, "meetings": 5}, "2026-10-03")
    ask, _ = scripted(["y", "p", "n", "inbox zero", "closed deal", "back-to-back meetings, waiting on legal",
                       "Overcommitment", "4", "6", "protect focus"])
    raw = checkins.ask_evening(["A", "B", "C"], "2026-10-03", ask=ask, out=lambda *_: None)
    res = checkins.run_evening(store, mock_llm, raw, "2026-10-03")
    assert [p["done"] for p in store.get_priorities("2026-10-03")] == [1.0, 0.5, 0.0]
    assert store.get_tags("2026-10-03") == ["dependencies", "meetings", "overcommitment"]
    ev = store.get_checkin("2026-10-03", "evening")
    assert (ev["energy"], ev["mood"], ev["meetings"]) == (4, 6, 5)  # meetings inherited from morning
    assert ev["data"]["wins"] == ["closed deal"] and ev["data"]["extra_done"] == ["inbox zero"]
    assert res["response"] == "Mocked Claude reply."


def test_evening_without_morning_uses_planned(store, dry_llm):
    res = checkins.run_evening(store, dry_llm, {"priorities": ["X", "Y"], "completed": [True, False],
                                                "energy": 6, "mood": 7}, "2026-10-04")
    assert "1 of 2" in res["response"] and "Suggestions for tomorrow:" in res["response"]


def test_llm_falls_back_on_refusal_and_error(store):
    llm = LLM(client=FakeClient(stop_reason="refusal"))
    assert llm.generate("s", "p", lambda: "templated") == "templated"

    class Boom:
        class beta:  # noqa: N801
            class messages:  # noqa: N801
                @staticmethod
                def create(**_):
                    raise ConnectionError("offline")
    assert LLM(client=Boom()).generate("s", "p", lambda: "templated") == "templated"


def test_llm_without_key_is_dry_run_and_non_fallback_models_use_plain_api():
    assert LLM().dry_run is True
    fc = FakeClient()
    LLM(model="claude-haiku-4-5", client=fc).generate("s", "p", lambda: "x")
    assert "fallbacks" not in fc.messages.calls[0] and "output_config" not in fc.messages.calls[0]


def test_auto_tags_and_status_parsing():
    assert checkins.auto_tags("Slack pings all day, I was exhausted") == ["interruptions", "low-energy"]
    assert [checkins.parse_status(v) for v in ("y", "partial", "no", 1, 0.5, False)] == [1, .5, 0, 1, .5, 0]
