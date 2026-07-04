import os
from pathlib import Path

import pytest

from mylar import variant_covers as vc


VARIANT_LIST = Path(__file__).resolve().parents[1] / "Variant filenames.txt"

# Series/collections — filename contains "variant" but is not an alternate cover issue.
NON_VARIANT_FILENAMES = {
    "Variants - A Jessica Jones Mystery (2023) (Digital-Empire).cbr",
    "Amazing Spider-Man newspaper strip [19790401-19790430](digital)(PeteThePIPster).cbz",
    "Amazing Spider-Man newspaper strip [19790301-19790331](digital)(PeteThePIPster).cbz",
    "Amazing Spider-Man newspaper strip [19790201-19790228](digital)(PeteThePIPster).cbz",
    "Marvel Fact Files 009 (2013)(digital)(PeteThePIPster).cbz",
    "Venomized - The Variant Covers (2020) (Digital) [Complete] (One-shot)",
    "The Variants 002 (2022) (Digital) (Zone-Empire).cbr",
    "Marvel's Hip-Hop Variant Guide (2016) (digital) (Minutemen-Thoth).cbz",
    "Carnage-ized - The Variant Covers 001 (2020) (Digital) (Zone-Empire).cbr",
    "Star Wars - The Action Figure Variant Covers (2020) (Digital) (Kileko-Empire).cbz",
    "Deadpool - The Variant Covers 001 (2020) (Digital) (Zone-Empire).cbr",
    "Peach.MoMoKo.the.Variant.Covers.001.(2020).(Digital).(Zone.Empire).cbr",
    "The Variants",
    "The Variants 005 (2023) (Digital) (Zone-Empire).cbr",
    "True Believers - Deadpool Variants (2016) (Digital) (Kileko-Empire).cbr",
    "Mister Miracle 001 Director's Cut (2018) (digital) (Son of Ultron-Empire).cbr",
    "Godzilla 001(2012)(3 covers)(Digital)(ComiXology Variant Edition)(TLK-EMPIRE-HD).cbr",
    "Godzilla 001(2012)(3 covers)(Digital)(IDW Variant Edition)(TLK-EMPIRE-HD).cbr",
}

VARIANT_SAMPLES = [
    ("Blood Hunt 001 (2024) Artgerm Variant (Digital) (MikeNY76).cbz", "Artgerm Variant"),
    ("DCeased 001 (2019) (VC - Greg Capullo) (digital-Empire).cbr", "VC - Greg Capullo"),
    ("Locke & Key - Crown of Shadows 04 (2010) (RI Cover Only) [extracted] (digital-Empire).cbr", "RI Cover Only"),
    ("Punisher 218 TV Variant (2017)(Digital)(cover only)(PeteThePIPster-Novus).cbz", "TV Variant"),
    ("Batman 031 (2014) (Incentive Mike Allred Batman 66 Variant Cover) (digital-Empire).cbr",
     "Incentive Mike Allred Batman 66 Variant Cover"),
    ("Metal Men 01 (2019) (Variant Cover) (Digital) (Phantom-SWA).cbr", "Variant Cover"),
    ("Wolverines 003 (Parel Variant) (2015) (Digital) (MikeNY76-Empire).cbz", "Parel Variant"),
]


def _load_variant_list_lines():
    if not VARIANT_LIST.is_file():
        return []
    lines = []
    with open(VARIANT_LIST, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line:
                lines.append(line)
    return lines


@pytest.mark.unit
@pytest.mark.parametrize("filename,descriptor", VARIANT_SAMPLES)
def test_variant_samples_match_and_extract(filename, descriptor):
    assert vc.is_variant_cover_filename(filename) is True
    assert vc.extract_variant_descriptor(filename) == descriptor


@pytest.mark.unit
@pytest.mark.parametrize("filename", sorted(NON_VARIANT_FILENAMES))
def test_non_variant_exclusions(filename):
    assert vc.is_variant_cover_filename(filename) is False


@pytest.mark.unit
def test_variant_list_coverage():
    lines = _load_variant_list_lines()
    if not lines:
        pytest.skip("Variant filenames.txt not present")
    missed = []
    false_pos = []
    for name in lines:
        hit = vc.is_variant_cover_filename(name)
        if name in NON_VARIANT_FILENAMES:
            if hit:
                false_pos.append(name)
        elif not hit:
            missed.append(name)
    assert not false_pos, "false positives: %s" % false_pos[:10]
    # Allow a small miss rate while patterns are refined; tighten as regex improves.
    miss_rate = len(missed) / max(len(lines) - len(NON_VARIANT_FILENAMES), 1)
    assert miss_rate < 0.05, "missed %d names (%.1f%%): %s" % (
        len(missed), miss_rate * 100, missed[:15])


@pytest.mark.unit
def test_size_gate_rejects_large_file(tmp_path):
    big = tmp_path / "Batman 001 (2025) (Jim Lee Variant) (Digital).cbz"
    big.write_bytes(b"x" * (vc.DEFAULT_MAX_VARIANT_BYTES + 1))
    info = vc.classify_variant_file(str(big))
    assert info["name_match"] is True
    assert info["size_ok"] is False
    assert info["is_variant"] is False


@pytest.mark.unit
def test_size_gate_accepts_small_file(tmp_path):
    small = tmp_path / "Batman 001 (2025) (Jim Lee Variant) (Digital).cbz"
    small.write_bytes(b"x" * 1024)
    info = vc.classify_variant_file(str(small))
    assert info["is_variant"] is True
    assert info["cover_only"] is False
    assert info["descriptor"] == "Jim Lee Variant"


@pytest.mark.unit
def test_cover_only_flag(tmp_path):
    path = tmp_path / "Willow 001 (2012) (New York Comic Con cover only) (digital).cbr"
    path.write_bytes(b"x")
    info = vc.classify_variant_file(str(path))
    assert info["is_variant"] is True
    assert info["cover_only"] is True


@pytest.mark.unit
def test_scan_series_variant_covers_upserts_and_prunes(tmp_path, monkeypatch):
    import mylar
    from mylar import db

    comic_dir = tmp_path / 'Batman'
    comic_dir.mkdir()
    variant_file = comic_dir / "Batman 001 (2025) (Jim Lee Variant) (Digital).cbz"
    variant_file.write_bytes(b'PK\x03\x04' + b'x' * 500)
    regular = comic_dir / "Batman 001 (2025) (Digital).cbz"
    regular.write_bytes(b'PK\x03\x04' + b'y' * 500)

    db_path = tmp_path / 'test.db'
    conn = __import__('sqlite3').connect(str(db_path))
    conn.execute(
        'CREATE TABLE comics (ComicID TEXT, ComicName TEXT, ComicLocation TEXT)'
    )
    conn.execute(
        "INSERT INTO comics VALUES ('12345', 'Batman', ?)",
        [str(comic_dir)],
    )
    conn.execute(
        'CREATE TABLE issues (IssueID TEXT, ComicID TEXT, Issue_Number TEXT, '
        'Int_IssueNumber INT, IssueDate TEXT)'
    )
    conn.execute(
        "INSERT INTO issues VALUES ('4000-99', '12345', '1', 1000, '2025-01-01')"
    )
    conn.execute(
        'CREATE TABLE variant_covers (VariantID TEXT UNIQUE, ComicID TEXT, IssueID TEXT, '
        'Issue_Number TEXT, Descriptor TEXT, Filename TEXT, Location TEXT UNIQUE, '
        'ComicSize TEXT, CoverOnly INTEGER, ThumbPath TEXT, DateAdded TEXT, DateUpdated TEXT)'
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(mylar, 'DB_FILE', str(db_path))
    monkeypatch.setattr(mylar, 'CONFIG', type('C', (), {'CACHE_DIR': str(tmp_path / 'cache'), 'MULTIPLE_DEST_DIRS': None})())
    monkeypatch.setattr(mylar, 'filers', type('F', (), {'FileHandlers': lambda ComicID=None: None})())

    count = vc.scan_series_variant_covers('12345', paths=[str(comic_dir)])
    assert count == 1

    myDB = db.DBConnection()
    rows = myDB.select('SELECT * FROM variant_covers WHERE ComicID=?', ['12345'])
    assert len(rows) == 1
    assert rows[0]['IssueID'] == '4000-99'
    assert 'Jim Lee' in (rows[0]['Descriptor'] or '')

    variant_file.unlink()
    vc.scan_series_variant_covers('12345', paths=[str(comic_dir)])
    rows = myDB.select('SELECT * FROM variant_covers WHERE ComicID=?', ['12345'])
    assert len(rows) == 0


@pytest.mark.unit
def test_scan_paths_yields_only_qualifying(tmp_path):
    good = tmp_path / "Storm 001 (2023) Artgerm Variant (Digital).cbz"
    good.write_bytes(b"x" * 100)
    bad_size = tmp_path / "Hulk 012 (2023) No Prize Variant (Digital).cbz"
    bad_size.write_bytes(b"x" * (vc.DEFAULT_MAX_VARIANT_BYTES + 100))
    not_variant = tmp_path / "Amazing Spider-Man 001.cbz"
    not_variant.write_bytes(b"x" * 100)
    found = list(vc.scan_paths([str(good), str(bad_size), str(not_variant)]))
    assert len(found) == 1
    assert found[0]["filename"] == good.name
