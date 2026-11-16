from collections import Counter

from matcher.generate_opportunities import NIGHT_FAMILIES, generate_opportunities


def test_counts_and_cities():
    df = generate_opportunities()
    assert Counter(df.type) == {"job": 30, "training": 15, "mentor": 5}
    jobs = df[df.type == "job"]
    assert Counter(jobs.city) == {"Hyderabad": 10, "Bengaluru": 5, "Chennai": 3, "Pune": 2, "Warangal": 2,
                                  "Visakhapatnam": 2, "Vijayawada": 1, "Remote": 5}


def test_remote_python_or_sql_jobs():
    jobs = generate_opportunities().query("type == 'job' and city == 'Remote'")
    n = sum(("python" in t.lower() or "sql" in t.lower()) for t in jobs.required_skills_text)
    assert n >= 2


def test_night_shift_only_support_and_soc():
    df = generate_opportunities()
    night = df[df.night_shift == "yes"]
    assert len(night) > 0 and set(night.job_family) <= NIGHT_FAMILIES


def test_remote_rows_use_remote_city():
    df = generate_opportunities()
    assert (df[df["mode"] == "remote"].city == "Remote").all()


def test_deterministic():
    assert generate_opportunities().equals(generate_opportunities())
