from tardigrade_skill.spec import SpecError, load_skill, validate_skill

from .conftest import VALID_SKILL_MD, make_skill


def test_valid_skill_passes(tmp_path):
    d = make_skill(tmp_path)
    meta, body, warns = load_skill(d)
    assert meta.name == "sample-skill"
    assert warns == []
    assert validate_skill(d) == []


def test_name_must_match_directory(tmp_path):
    d = make_skill(tmp_path, name="other-name")
    problems = validate_skill(d)
    assert any("must match the parent directory" in p for p in problems)


def test_name_uppercase_rejected(tmp_path):
    md = VALID_SKILL_MD.replace("name: sample-skill", "name: Sample-Skill")
    d = make_skill(tmp_path, skill_md=md)
    assert validate_skill(d) != []


def test_name_consecutive_hyphens_rejected(tmp_path):
    md = VALID_SKILL_MD.replace("name: sample-skill", "name: sample--skill")
    d = make_skill(tmp_path, skill_md=md)
    assert validate_skill(d) != []


def test_description_too_long_rejected(tmp_path):
    md = VALID_SKILL_MD.replace(
        "description: A benign sample skill used in tests. Use when testing tardigrade-skill.",
        "description: " + "x" * 1025,
    )
    d = make_skill(tmp_path, skill_md=md)
    assert validate_skill(d) != []


def test_unknown_frontmatter_field_is_warning(tmp_path):
    md = VALID_SKILL_MD.replace("license: MIT", "license: MIT\nallow-everything: true")
    d = make_skill(tmp_path, skill_md=md)
    meta, body, warns = load_skill(d)
    assert any("unexpected frontmatter fields" in w for w in warns)


def test_missing_skill_md(tmp_path):
    d = tmp_path / "empty-skill"
    d.mkdir()
    assert validate_skill(d) != []
