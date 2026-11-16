from matcher.explain import fact_check, template_reason
from matcher.schema import CheckResult, TopMatch
from matcher.skills import load_vocab

from .conftest import make_opp, make_student

ok = CheckResult(status="pass", note="")


def match(**kw):
    base = dict(rank=1, opp_id="O1", title="Junior Data Analyst", type="job", city="Remote", mode="remote",
                final_score=0.8, overlap=["Python", "SQL", "Excel"], missing=["Power BI"],
                checks={"location": ok, "budget": ok, "language": ok, "family": ok}, reason="")
    base.update(kw)
    return TopMatch(**base)


def test_template_exact_string():
    opp = make_opp(title="Junior Data Analyst", city="Remote", mode="remote", pay_min=360000, pay_max=360000)
    assert template_reason(match(), make_student(), opp) == (
        "Matches your Python, SQL and Excel skills. Remote, no need to move. Pay about 3.6 LPA. "
        "Learn Power BI to improve fit.")


def test_template_training_and_unknown_check():
    opp = make_opp(type="training", city="Hyderabad", mode="onsite", pay_min=None, pay_max=None, upfront_cost=12000)
    m = match(type="training", city="Hyderabad", mode="onsite", overlap=[], missing=["Selenium"],
              checks={"location": CheckResult(status="unknown", note="relocation not confirmed"),
                      "budget": ok, "language": ok, "family": ok})
    text = template_reason(m, make_student(), opp)
    assert text == ("Builds skills in Selenium. Needs a move to Hyderabad. Costs Rs 12000. "
                    "Check: relocation not confirmed.")


def test_fact_check_rejects_unlisted_skill_and_city():
    facts = {"title": "Data Analyst", "city": "Hyderabad", "overlap": ["Python"], "missing": ["SQL"],
             "pay_lpa": 3.6, "upfront_cost": 0}
    v = load_vocab()
    assert not fact_check("Matches your Java skill", facts, v)
    assert not fact_check("Based in Pune", facts, v)
    assert not fact_check("Pays 9 LPA", facts, v)
    assert not fact_check("word " * 41, facts, v)
    assert fact_check("Matches your Python skill and pays about 3.6 LPA in Hyderabad", facts, v)


def test_template_used_with_no_provider():
    from matcher.explain import fill_reasons
    opp = make_opp(opp_id="O1", title="Junior Data Analyst", city="Remote", mode="remote")
    out = fill_reasons(make_student(), [match()], {"O1": opp})
    assert out[0].reason_method == "template" and out[0].reason


def lakshmi_like():
    """Two analyst jobs from one family, a mentor that teaches the gap, and a weak, low-paid job."""
    opps = {
        "J1": make_opp(opp_id="J1", job_family="Data Analyst", pay_min=360000, pay_max=360000),
        "J2": make_opp(opp_id="J2", job_family="Data Analyst", pay_min=420000, pay_max=420000),
        "M1": make_opp(opp_id="M1", type="mentor", job_family="Mentorship", pay_min=None, pay_max=None),
        "M2": make_opp(opp_id="M2", type="mentor", job_family="Mentorship", pay_min=None, pay_max=None),
        "J3": make_opp(opp_id="J3", job_family="ML Intern", pay_min=120000, pay_max=120000),
    }
    ms = [
        match(rank=1, opp_id="J1", overlap=["Excel", "SQL"], missing=[]),
        match(rank=2, opp_id="J2", overlap=["Excel", "SQL", "Python"], missing=["Power BI"]),
        match(rank=3, opp_id="M1", type="mentor", overlap=["Excel", "SQL"], missing=["Power BI"]),
        match(rank=4, opp_id="M2", type="mentor", overlap=["Python"], missing=["Django"]),
        match(rank=5, opp_id="J3", overlap=["Python"], missing=["Pandas", "Scikit-learn"], fit="Possible fit"),
    ]
    return ms, opps


def test_headline_compares_matches_instead_of_repeating_tags():
    from matcher.explain import headline
    ms, opps = lakshmi_like()
    lines = [headline(m, ms, opps) for m in ms]
    assert lines == [
        "You already have every skill this role asks for, so you can apply as you are.",
        "The same kind of role as your first match, and it pays more. It also asks for Power BI, which you don't have yet.",
        "A mentor who can help you learn Power BI, which your job matches ask for.",
        "A mentor in skills outside your job matches, such as Django.",
        "A stretch: you have 1 of the 3 skills it asks for. It pays the least of your job matches.",
    ]
    for line in lines:   # the tags already show place and pay amounts, so the headline does not
        assert "Remote" not in line and "LPA" not in line and "Rs" not in line


def test_headline_is_filled_and_reason_is_kept():
    from matcher.explain import fill_reasons
    ms, opps = lakshmi_like()
    out = fill_reasons(make_student(), ms, opps)
    assert all(m.headline for m in out)
    assert out[0].reason.startswith("Matches your Excel and SQL skills")


def test_headline_for_training_and_no_job_matches():
    from matcher.explain import headline
    opps = {"T1": make_opp(opp_id="T1", type="training", pay_min=None, pay_max=None),
            "M1": make_opp(opp_id="M1", type="mentor", pay_min=None, pay_max=None)}
    t = match(rank=1, opp_id="T1", type="training", overlap=[], missing=["Selenium"], teaches=["Selenium"])
    mm = match(rank=2, opp_id="M1", type="mentor", overlap=["Python"], missing=["Django"])
    assert headline(t, [t, mm], opps) == "Teaches Selenium, which the jobs that fit you best ask for."
    assert headline(mm, [t, mm], opps) == "A mentor who can help you learn Django."


def test_weak_related_credit_is_not_put_in_the_reason():
    opp = make_opp(city="Remote", mode="remote")
    weak = match(related=[{"have": "Excel", "need": "Pandas", "credit": 0.2}, {"have": "Excel", "need": "Power BI", "credit": 0.3}])
    assert "counts for" not in template_reason(weak, make_student(), opp)
    mixed = match(related=[{"have": "Excel", "need": "Pandas", "credit": 0.2}, {"have": "MySQL", "need": "SQL", "credit": 0.8}])
    assert "Your MySQL also counts for SQL" in template_reason(mixed, make_student(), opp)
