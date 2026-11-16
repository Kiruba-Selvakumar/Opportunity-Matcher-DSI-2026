import numpy as np

from matcher.embed import get_encoder, profile_vector
from matcher.generate_students import SKILL_POOLS, SOFT_SKILLS, LOCAL_SKILLS
from matcher.generate_opportunities import FAMILIES
from matcher.skills import load_synonyms, load_vocab, normalize


def test_vocab_size_and_unique():
    v = load_vocab()
    assert 140 <= len(v) <= 160 and len(set(v)) == len(v)


def test_synonyms_point_to_vocab():
    v = set(load_vocab())
    syn = load_synonyms()
    assert sum(len(x) for x in syn.values()) >= 60
    assert all(c in v for cs in syn.values() for c in cs)


def test_generator_pools_are_in_vocab():
    v = set(load_vocab())
    pools = {s for p in SKILL_POOLS.values() for s in p} | set(SOFT_SKILLS) | set(LOCAL_SKILLS)
    for _, _, skills, _ in FAMILIES:
        for s in skills:
            pools |= set(s) if isinstance(s, tuple) else {s}
    assert pools <= v, pools - v


def test_normalize_examples():
    got, unmatched = normalize(["py", "dsa", "reactjs", "html css"])
    assert got == ["Python", "Data Structures", "Algorithms", "React", "HTML", "CSS"] and unmatched == []


def test_unknown_goes_to_unmatched():
    got, unmatched = normalize(["cooking", "Python"])
    assert got == ["Python"] and unmatched == ["cooking"]


def test_vectors_normalized_or_zero():
    enc = get_encoder()
    assert enc.method == "tfidf"
    v = profile_vector(["Python", "SQL"], enc)
    assert abs(np.linalg.norm(v) - 1) < 1e-5
    assert not np.any(profile_vector([], enc))
