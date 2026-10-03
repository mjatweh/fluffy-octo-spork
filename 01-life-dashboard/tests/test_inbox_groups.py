from datetime import datetime, timedelta

from life_dashboard.briefing import template_briefing
from life_dashboard.models import DayData, Email
from life_dashboard.normalize import normalize_emails, tag_emails
from life_dashboard.render import render_html

T0 = datetime(2026, 10, 5, 8, 0)


def mail(sender, subject="Can you review?", minutes=0, **kw):
    return Email(sender, subject, T0 + timedelta(minutes=minutes), **kw)


def test_tag_emails_sets_group_and_flags_work_in_personal_inbox():
    personal = [mail("Dana <dana@acme-fund.com>"), mail("Mom <mom@gmail.com>"), mail("boss@Partner.io"),
                mail("ops@mail.acme-fund.com"), mail("x@notacme-fund.com")]
    tag_emails(personal, {"group": "Personal", "work_reply_from": "me@company.com",
                          "work_domains": ["acme-fund.com"], "work_senders": ["boss@partner.io"]}, "Gmail")
    assert {m.group for m in personal} == {"Personal"}
    assert [m.reply_from for m in personal] == ["me@company.com", "", "me@company.com", "me@company.com", ""]


def test_group_defaults_to_connector_name_and_no_routing_without_reply_from():
    work = [mail("dana@acme-fund.com")]
    tag_emails(work, {"work_domains": ["acme-fund.com"]}, "Work mail")
    assert work[0].group == "Work mail" and work[0].reply_from == ""


def test_limit_is_per_group_and_groups_keep_config_order():
    emails = [mail(f"a{i}@work.com", minutes=i, group="Work") for i in range(5)]
    emails += [mail("urgent@gmail.com", minutes=99, flagged=True, group="Personal")]
    kept = normalize_emails(emails, limit=2)
    assert [m.group for m in kept] == ["Work", "Work", "Personal"]  # Work first, as configured


def test_briefing_and_dashboard_show_groups_and_reply_from(config, day):
    data = DayData(day=day, generated_at=T0.replace(tzinfo=config.tz))
    data.emails = normalize_emails([
        mail("Dana Lee <dana@acme-fund.com>", "Term sheet questions?", group="Personal", reply_from="me@company.com"),
        mail("CFO <cfo@client.com>", "Can you send the forecast?", group="Client"),
    ])
    lines = template_briefing(data).emails_to_reply
    assert "[Personal] Dana Lee: Term sheet questions? (reply from me@company.com)" in lines
    assert "[Client] CFO: Can you send the forecast?" in lines
    html = render_html(data, template_briefing(data))
    assert '<h3 class="group">Personal' in html and '<h3 class="group">Client' in html
    assert "Reply from me@company.com" in html
    prompt = data.to_prompt_dict()["emails"]
    assert prompt[0]["group"] == "Personal" and prompt[0]["reply_from"] == "me@company.com"


def test_single_group_has_no_section_headings(config, day):
    data = DayData(day=day, generated_at=T0.replace(tzinfo=config.tz))
    data.emails = normalize_emails([mail("x@y.com", group="Inbox")])
    assert '<h3 class="group">' not in render_html(data, template_briefing(data))
    assert template_briefing(data).emails_to_reply == ["x@y.com: Can you review?"]
