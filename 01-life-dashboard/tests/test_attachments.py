import base64
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from life_dashboard import attachments as at

NY = ZoneInfo("America/New_York")
RULES = [
    at.Rule("Insurance", senders=["insureco.com"], keywords=["policy", "renewal"]),
    at.Rule("Work", inboxes=["Work mail"], keywords=["agreement"]),
]


def raw_email(sender, subject, files, msg_id="<m1@x>"):
    msg = EmailMessage()
    msg["From"], msg["Subject"], msg["Message-ID"] = sender, subject, msg_id
    msg["Date"] = "Mon, 05 Oct 2026 10:00:00 -0400"
    msg.set_content("see attached")
    for name, data in files:
        maintype, subtype = ("application", "pdf") if name.endswith(".pdf") else ("image", "png")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return msg.as_bytes()


def test_rule_matching():
    assert at.first_match(RULES, "Personal", "agent@insureco.com", "hello").name == "Insurance"
    assert at.first_match(RULES, "Personal", "a@mail.insureco.com", "hello").name == "Insurance"
    assert at.first_match(RULES, "Personal", "a@notinsureco.com", "hello") is None
    assert at.first_match(RULES, "Personal", "x@y.com", "Your Policy renewal").name == "Insurance"
    assert at.first_match(RULES, "Personal", "x@y.com", "hi", ["Auto-Policy.pdf"]).name == "Insurance"
    assert at.first_match(RULES, "Personal", "x@y.com", "policyholder news") is None  # whole words only
    assert at.first_match(RULES, "Personal", "x@y.com", "Signed agreement") is None  # Work rule: other inbox
    assert at.first_match(RULES, "Work mail", "x@y.com", "Signed agreement").name == "Work"


def test_only_pdf_and_word_files_are_kept():
    import email

    msg = email.message_from_bytes(raw_email("a@b.com", "s", [("Policy.pdf", b"%PDF-1"), ("logo.png", b"img")]))
    assert at.files_from_message(msg, ["pdf", "docx"]) == [("Policy.pdf", b"%PDF-1")]


def test_save_names_and_dedupes(tmp_path):
    f = at.Found("Personal", "<1>", "a@b.com", "s", datetime(2026, 10, 5, tzinfo=NY),
                 [("Auto: Policy?.pdf", b"one")])
    assert [p.name for p in at.save(f, tmp_path)] == ["2026-10-05 Auto Policy.pdf"]
    assert at.save(f, tmp_path) == []  # same bytes: not written again
    f.files = [("Auto: Policy?.pdf", b"two")]
    (new,) = at.save(f, tmp_path)
    assert new.name.startswith("2026-10-05 Auto Policy ") and new.read_bytes() == b"two"


class FakeIMAP:
    def __init__(self, messages):
        self.messages = messages  # uid -> raw bytes
        self.commands = []

    def login(self, user, password):
        pass

    def select(self, mailbox, readonly=False):
        assert readonly
        self.mailbox = mailbox

    def uid(self, command, *args):
        self.commands.append((command, args))
        if command == "SEARCH":
            return "OK", [b" ".join(self.messages)]
        uid, what = args
        assert "PEEK" in what  # never marks mail as read
        raw = self.messages[uid]
        if "HEADER.FIELDS" in what:
            raw = raw.split(b"\n\n", 1)[0] + b"\n\n"
        return "OK", [(b"meta", raw)]


def test_imap_scan_gmail():
    conn = FakeIMAP({
        b"1": raw_email("agent@insureco.com", "Docs", [("Dec page.pdf", b"%PDF")], "<a@x>"),
        b"2": raw_email("friend@x.com", "Party pics", [("pic.pdf", b"%PDF")], "<b@x>"),
        b"3": raw_email("friend@x.com", "fyi", [("Home Policy.pdf", b"%PDF")], "<c@x>"),
    })
    seen: set[str] = set()
    options = {"name": "Personal", "host": "imap.gmail.com", "username": "me@gmail.com"}
    since = datetime.now(timezone.utc) - timedelta(days=30)
    found = at.imap_scan(conn, options, "pw", RULES, seen, since, ["pdf"], NY)
    assert conn.mailbox == at.GMAIL_ALL
    assert "has:attachment newer_than:30d" in conn.commands[0][1][1]
    assert sorted(f.message_id for f in found) == ["<a@x>", "<c@x>"]
    assert seen == {"<b@x>"}  # non-matching mail is remembered so it isn't downloaded again
    found = at.imap_scan(conn, options, "pw", RULES, seen | {"<a@x>", "<c@x>"}, since, ["pdf"], NY)
    assert found == []


def test_graph_scan():
    pdf = base64.b64encode(b"%PDF").decode()
    pages = {
        "messages": {"value": [
            {"id": "m1", "subject": "Signed agreement", "from": {"emailAddress": {"address": "x@y.com"}},
             "receivedDateTime": "2026-10-05T14:00:00Z", "internetMessageId": "<g1>"},
            {"id": "m2", "subject": "Newsletter", "from": {"emailAddress": {"address": "x@y.com"}},
             "receivedDateTime": "2026-10-05T14:00:00Z", "internetMessageId": "<g2>"},
        ]},
        "m1": {"value": [{"@odata.type": "#microsoft.graph.fileAttachment", "name": "SAFE.pdf", "size": 4,
                          "contentBytes": pdf},
                         {"@odata.type": "#microsoft.graph.fileAttachment", "name": "sig.png", "size": 4,
                          "contentBytes": pdf, "isInline": True}]},
        "m2": {"value": [{"@odata.type": "#microsoft.graph.fileAttachment", "name": "news.pdf", "size": 4,
                          "contentBytes": pdf}]},
    }

    def request(url, token=None):
        assert token == "tok"
        if "/attachments" in url:
            return pages[url.split("/messages/")[1].split("/")[0]]
        assert "hasAttachments" in url
        return pages["messages"]

    seen: set[str] = set()
    found = at.graph_scan(request, "tok", "Work mail", RULES, seen, datetime.now(timezone.utc), ["pdf"], NY)
    assert [(f.message_id, f.files) for f in found] == [("<g1>", [("SAFE.pdf", b"%PDF")])]
    assert seen == {"<g2>"}


def test_run_without_rules_does_nothing(tmp_path, config, capsys):
    assert at.run(config, rules_file=tmp_path / "missing.toml") == 0
    assert "nothing to import" in capsys.readouterr().out
