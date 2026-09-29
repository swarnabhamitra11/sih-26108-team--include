import pytest
from scripts.import_seed import validate_seeds, load_seeds

def test_validate_natural_keys_regression(tmp_path):
    """Regression test ensuring validate_seeds works with current natural-key headers and utf-8-sig."""
    standards_csv = tmp_path / "standards.csv"
    editions_csv = tmp_path / "standard_editions.csv"
    amendments_csv = tmp_path / "standard_amendments.csv"
    relations_csv = tmp_path / "standard_relations.csv"

    # Write BOM-prefixed CSVs with real rows and current headers
    standards_content = (
        "\ufeffis_number,part,title,product_group,category,scope_text,keywords,status,superseded_by_is_number,superseded_by_part,source_url,source_note\n"
        'IS 269,,Ordinary portland cement - Specification,Cement,material,Covers requirements for ordinary Portland cement.,"cement, ordinary Portland, OPC, general construction, specification",current,,,https://standards.bis.gov.in/example,note\n'
        'IS 1489,1,Portland Pozzolana Cement - Specification: Part 1,Cement,material,Covers fly ash based Portland pozzolana cement.,"cement, Portland pozzolana, fly ash, PPC, specification",current,,,https://standards.bis.gov.in/example,note\n'
        'IS 1139,,Hot rolled mild steel,Steel,material,Covers mild steel specifications.,"steel, mild steel, rebar, construction, specification",superseded,IS 1786,,https://standards.bis.gov.in/example,note\n'
        'IS 1786,,High strength deformed steel bars,Steel,material,Covers deformed steel bars.,"steel, deformed bars, HSD, rebar, specification",current,,,https://standards.bis.gov.in/example,note\n'
    )
    standards_csv.write_text(standards_content, encoding="utf-8")

    editions_content = (
        "\ufeffis_number,part,edition_year,is_latest,notes\n"
        'IS 269,,2015,TRUE,Latest edition\n'
        'IS 1489,1,1991,FALSE,Older edition\n'
        'IS 1489,1,2015,TRUE,Latest edition\n'
        'IS 1786,,2008,TRUE,Latest edition\n'
    )
    editions_csv.write_text(editions_content, encoding="utf-8")

    amendments_content = (
        "\ufeffis_number,part,edition_year,amendment_no,year,notes\n"
        'IS 269,,2015,1,2023,First Amendment\n'
        'IS 1489,1,2015,1,2018,First Amendment\n'
    )
    amendments_csv.write_text(amendments_content, encoding="utf-8")

    relations_content = (
        "\ufefffrom_is_number,from_part,to_is_number,to_part,relation_type,notes\n"
        'IS 269,,IS 1489,1,normative_ref,Referred standard\n'
    )
    relations_csv.write_text(relations_content, encoding="utf-8")

    seeds = load_seeds(tmp_path)
    errors = validate_seeds(seeds)
    assert errors == [], f"Validation should succeed with 0 errors, got: {errors}"


def test_benchmark_rules_validation(tmp_path):
    """Test validation of benchmark rules:
    - kind='abstain' must have zero expected rows
    - kind='normal' must have at least one 'primary' row
    - verified query requires all its standards to be verified
    """
    standards_csv = tmp_path / "standards.csv"
    editions_csv = tmp_path / "standard_editions.csv"
    amendments_csv = tmp_path / "standard_amendments.csv"
    relations_csv = tmp_path / "standard_relations.csv"
    bench_rows_csv = tmp_path / "benchmark_rows.csv"
    bench_exp_csv = tmp_path / "benchmark_expected.csv"

    # Base valid seed
    standards_csv.write_text(
        "is_number,part,title,product_group,category,scope_text,keywords,status,verification_status,superseded_by_is_number,superseded_by_part,source_url,source_note\n"
        "IS 0001,,Standard One,Cement,material,Scope one.,\"k1, k2, k3, k4, k5\",current,entered,,,https://example.com,note\n"
        "IS 0002,,Standard Two,Steel,material,Scope two.,\"k1, k2, k3, k4, k5\",current,verified,,,https://example.com,note\n",
        encoding="utf-8",
    )
    editions_csv.write_text("is_number,part,edition_year,is_latest,notes\nIS 0001,,2020,TRUE,\nIS 0002,,2020,TRUE,\n", encoding="utf-8")
    amendments_csv.write_text("is_number,part,edition_year,amendment_no,year,notes\n", encoding="utf-8")
    relations_csv.write_text("from_is_number,from_part,to_is_number,to_part,relation_type,notes\n", encoding="utf-8")

    # 1. Invalid abstain (has expected row)
    bench_rows_csv.write_text("query,kind,verification_status\nUnrelated query,abstain,entered\n", encoding="utf-8")
    bench_exp_csv.write_text("query,is_number,part,role\nUnrelated query,IS 0001,,primary\n", encoding="utf-8")
    seeds = load_seeds(tmp_path)
    errs = validate_seeds(seeds)
    assert any("abstain rule violation" in e and "has 1 benchmark_expected" in e for e in errs)

    # 2. Invalid normal (has no primary row)
    bench_rows_csv.write_text("query,kind,verification_status\nNormal query,normal,entered\n", encoding="utf-8")
    bench_exp_csv.write_text("query,is_number,part,role\nNormal query,IS 0001,,allied\n", encoding="utf-8")
    seeds = load_seeds(tmp_path)
    errs = validate_seeds(seeds)
    assert any("has no 'primary' expected standard" in e for e in errs)

    # 3. Invalid verified status (references standard with status 'entered')
    bench_rows_csv.write_text("query,kind,verification_status\nGood query,normal,verified\n", encoding="utf-8")
    bench_exp_csv.write_text("query,is_number,part,role\nGood query,IS 0001,,primary\n", encoding="utf-8")
    seeds = load_seeds(tmp_path)
    errs = validate_seeds(seeds)
    assert any("verification rule violation" in e and "is 'entered'" in e for e in errs)

    # 4. Valid combination
    bench_rows_csv.write_text("query,kind,verification_status\nGood query,normal,verified\n", encoding="utf-8")
    bench_exp_csv.write_text("query,is_number,part,role\nGood query,IS 0002,,primary\n", encoding="utf-8")
    seeds = load_seeds(tmp_path)
    errs = validate_seeds(seeds)
    assert errs == []
