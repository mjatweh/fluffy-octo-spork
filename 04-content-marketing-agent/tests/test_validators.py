from content_agent import schemas as s
from content_agent.validators import X_LIMIT, enforce, find_banned, normalize, validate, x_length


def test_x_char_limit():
    assert validate(s.XPost("a" * 280)) == []
    issues = validate(s.XPost("a" * 281))
    assert issues and "281" in issues[0] and "280" in issues[0]


def test_x_urls_count_as_23():
    text = "x" * 250 + " https://example.com/a/very/long/path/that/is/long"
    assert x_length(text) == 250 + 1 + 23
    assert validate(s.XPost(text)) == []


def test_thread_validation():
    assert any("tweets: 2 items" in i for i in validate(s.XThread(["one", "two"])))
    issues = validate(s.XThread(["ok", "b" * 300, "ok"]))
    assert issues == ["tweet 2 is 300 chars (max 280)"]


def test_banned_words_case_insensitive_whole_word():
    post = s.XPost("We Leverage AI and keep leveraging it. Leverages too.")
    assert find_banned(post, ["leverage"]) == ["banned word 'leverage' used in text"]
    assert find_banned(s.XPost("Clever average"), ["leverage"]) == []
    assert find_banned(s.XPost("a game-changer"), ["game-changer"])
    assert find_banned(s.XPost("change the game"), ["game-changer"]) == []


def test_banned_words_found_in_nested_fields():
    ig = s.InstagramPost("cap", ["a"] * 5, [s.CarouselSlide("t", "pure synergy", "v")] * 3)
    assert any("slides[0].body" in i for i in validate(ig, ["synergy"]))


def test_hashtag_and_count_limits():
    li = s.LinkedInPost("hook", "body", "cta", ["a", "b"])
    assert any("hashtags: 2 items" in i for i in validate(li))
    assert normalize(s.LinkedInPost("h", "b", "c", ["#AI", " Ops Team "])).hashtags == ["AI", "OpsTeam"]


def test_landing_page_rejects_invented_testimonials():
    lp = s.LandingPage("H", "S", "Go", [s.Benefit("a", "b")] * 3, ["\"Great!\" - Jane", "[Logo]"],
                       [s.FAQ("q", "a")] * 4, "cta")
    assert validate(lp) == ["social_proof 1 must be a [placeholder], not an invented testimonial"]


def test_ad_limits_and_enforce():
    ad = s.AdCopy([s.AdVariant("a", "H" * 41, "P" * 10, "D" * 31)] * 3)
    issues = validate(ad)
    assert any("headline is 41" in i for i in issues) and any("description is 31" in i for i in issues)
    assert validate(enforce(ad)) == []


def test_enforce_trims_tweets():
    t = enforce(s.XThread(["word " * 80, "fine", "fine"]))
    assert all(x_length(x) <= X_LIMIT for x in t.tweets) and t.tweets[0].endswith("…")


def test_newsletter_subject_limits():
    nl = s.Newsletter(["x" * 61, "ok", "ok"], "p", "t", [s.NewsletterSection("h", "b")] * 2, "c", "u", "bye")
    assert validate(nl) == ["subject line 1 is 61 chars (max 60)"]


def test_video_word_budget():
    v = s.VideoScript("hook", ["word " * 100], "cta", 20, [s.Shot("0:00", "v", "vo", "")] * 3)
    assert any("too long for 20s" in i for i in validate(v))
