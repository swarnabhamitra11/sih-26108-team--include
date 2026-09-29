import pytest
from app.services.designation import parse_designation, Designation, find_designations

# Table‑driven test cases for parse_designation
TEST_CASES = [
    # (input string, expected Designation tuple)
    ("IS 456 : 2000",            Designation(base_is_number='IS 456', part=None, year=2000)),
    ("IS456:2000",              Designation(base_is_number='IS 456', part=None, year=2000)),
    ("is 456 : 2000",           Designation(base_is_number='IS 456', part=None, year=2000)),
    ("IS 1489 (Part 1) : 1991", Designation(base_is_number='IS 1489', part='1', year=1991)),
    ("IS 1489 (Part 1)",        Designation(base_is_number='IS 1489', part='1', year=None)),
    ("IS 2405 : Part 1 : 1980", Designation(base_is_number='IS 2405', part='1', year=1980)),
    ("IS 9873(P-4):2017",       Designation(base_is_number='IS 9873', part='4', year=2017)),
    ("IS 456-2000",             Designation(base_is_number='IS 456', part=None, year=2000)),
    ("IS 1489-1:1991",          Designation(base_is_number='IS 1489', part='1', year=1991)),
    ("IS/ISO 10434",            Designation(base_is_number='IS/ISO 10434', part=None, year=None)),
    ("IS 269:2015 (Reaffirmed 2020)", Designation(base_is_number='IS 269', part=None, year=2015)),
    ("IS 432 (Annex A)",        Designation(base_is_number='IS 432', part=None, year=None)),
    # non‑IS inputs should return empty designations
    ("",                         Designation(base_is_number='', part=None, year=None)),
    ("hello",                    Designation(base_is_number='', part=None, year=None)),
    ("IS",                       Designation(base_is_number='', part=None, year=None)),
    ("ISO 9001:2015",            Designation(base_is_number='', part=None, year=None)),
    ("BS 5950",                  Designation(base_is_number='', part=None, year=None)),
]

@pytest.mark.parametrize("input_str,expected", TEST_CASES)
def test_parse_designation(input_str, expected):
    assert parse_designation(input_str) == expected


def test_find_designations_deduplication():
    text = "as per IS 456:2000 and IS 1489 (Part 1), see also IS 456:2000"
    results = find_designations(text)
    expected = [
        Designation(base_is_number='IS 456', part=None, year=2000),
        Designation(base_is_number='IS 1489', part='1', year=None),
    ]
    assert results == expected
