"""Grader tests: hand-written answer strings with known expected results."""

import pytest

from errorbars.grade import extract_answer, grade

CASES = [
    # (model output, gold, expected correct, expected extracted)
    ("Working... #### 42", "42", 1, "42"),
    ("Working... #### 42.0", "42", 1, "42"),
    ("The total is $1,200 in all. #### 1200", "1200", 1, "1200"),
    ("She has 3 apples and buys 4 more. #### 7", "7", 1, "7"),
    ("#### -5", "-5", 1, "-5"),
    ("Answer: #### 3.5", "3.5", 1, "3.5"),
    ("Answer: #### 3.50", "3.5", 1, "3.5"),
    ("He ran 10 miles, then 5 more, so 15. #### 15", "15", 1, "15"),
    ("#### 1,000,000", "1000000", 1, "1000000"),
    ("So the answer is 8.", "8", 1, "8"),                    # no marker: last number
    ("There are 12 eggs in a dozen, he bought 2 dozen: 24", "24", 1, "24"),
    ("First try #### 9, wait, recompute: #### 11", "11", 1, "11"),  # last marker wins
    ("#### 42", "43", 0, "42"),                               # wrong answer
    ("The result is 100 dollars. #### 99", "100", 0, "99"),   # marker beats prose
    ("#### $2,500.0", "2500", 1, "2500"),
    ("Half of 7 is 3.5 #### 3.5", "7", 0, "3.5"),
    ("No numbers here at all.", "5", 0, None),                # unparsable
    ("", "5", 0, None),                                       # empty
    (None, "5", 0, None),                                     # missing text
    ("#### ", "5", 0, None),                                  # marker, no number anywhere
    ("He earns 20% of 50, which is 10. #### 10", "10", 1, "10"),
    ("#### 0", "0", 1, "0"),
]


@pytest.mark.parametrize("text,gold,correct,extracted", CASES)
def test_grade_cases(text, gold, correct, extracted):
    got_correct, got_extracted = grade(text, gold)
    assert got_correct == correct
    assert got_extracted == extracted


def test_extract_ignores_earlier_marker():
    assert extract_answer("#### 1 and then #### 2") == "2"
