import os
import zipfile
from io import BytesIO
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
    assert (comic_dir / vc.VARIANT_SUBFOLDER_NAME / variant_file.name).is_file()
    assert not variant_file.is_file()

    myDB = db.DBConnection()
    rows = myDB.select('SELECT * FROM variant_covers WHERE ComicID=?', ['12345'])
    assert len(rows) == 1
    assert rows[0]['IssueID'] == '4000-99'
    assert 'Jim Lee' in (rows[0]['Descriptor'] or '')
    assert vc.VARIANT_SUBFOLDER_NAME in rows[0]['Location']

    moved = comic_dir / vc.VARIANT_SUBFOLDER_NAME / variant_file.name
    moved.unlink()
    vc.scan_series_variant_covers('12345', paths=[str(comic_dir)])
    rows = myDB.select('SELECT * FROM variant_covers WHERE ComicID=?', ['12345'])
    assert len(rows) == 0


@pytest.mark.unit
def test_pick_cover_member_prefers_single_image():
    assert vc._pick_cover_member(['pages/scan.png']) == 'pages/scan.png'


@pytest.mark.unit
def test_pick_cover_member_prefers_cover_name():
    members = ['002.jpg', 'cover.jpg', '001.jpg']
    assert vc._pick_cover_member(members) == 'cover.jpg'


@pytest.mark.unit
def test_read_variant_cover_jpeg_from_cbz(tmp_path, monkeypatch):
    import mylar

    cbz = tmp_path / 'Batman 001 (Jim Lee Variant).cbz'
    try:
        from PIL import Image
    except ImportError:
        pytest.skip('PIL not available')
    buf = BytesIO()
    Image.new('RGB', (800, 1200), color=(20, 40, 200)).save(buf, format='PNG')
    png = buf.getvalue()
    with zipfile.ZipFile(cbz, 'w') as zf:
        zf.writestr('cover.png', png)

    cache = tmp_path / 'cache'
    monkeypatch.setattr(mylar, 'CONFIG', type('C', (), {'CACHE_DIR': str(cache)})())

    thumb = vc.read_variant_cover_jpeg(str(cbz), variant_id='abc', max_width=600)
    assert thumb and thumb[:3] == b'\xff\xd8\xff'
    full = vc.read_variant_cover_jpeg(str(cbz), variant_id='abc', max_width=None)
    assert full and full[:3] == b'\xff\xd8\xff'
    assert len(full) >= len(thumb)


@pytest.mark.unit
def test_resolve_variant_location_finds_variants_subfolder(tmp_path):
    series = tmp_path / 'Batman (2023)'
    series.mkdir()
    variants = series / vc.VARIANT_SUBFOLDER_NAME
    variants.mkdir()
    cbz = variants / 'Batman 001 (Jim Lee Variant).cbz'
    cbz.write_bytes(b'PK')
    stale = str(series / cbz.name)
    resolved = vc.resolve_variant_location(stale, comic_location=str(series), filename=cbz.name)
    assert resolved == str(cbz)


@pytest.mark.unit
def test_variant_cover_cache_url(tmp_path, monkeypatch):
    import mylar

    cache_root = tmp_path / 'cache'
    thumb = cache_root / 'variant_covers' / 'abc_thumb.jpg'
    thumb.parent.mkdir(parents=True)
    thumb.write_bytes(b'\xff\xd8\xff')
    monkeypatch.setattr(mylar, 'CONFIG', type('C', (), {'CACHE_DIR': str(cache_root)})())
    assert vc.variant_cover_cache_url(str(thumb)) == 'cache/variant_covers/abc_thumb.jpg'


@pytest.mark.unit
def test_extract_issue_number_from_supergirl_filenames():
    variant = (
        'Supergirl - Woman of Tomorrow 001 (2021) (Blank Variant) '
        '(Digital) (MikeNY76-Empire).cbz'
    )
    main = 'Supergirl - Woman of Tomorrow 01 (of 08) (2021) (digital).cbr'
    assert vc._extract_issue_number_from_filename(variant) == '001'
    assert vc._extract_issue_number_from_filename(main) == '01'


@pytest.mark.unit
def test_normalize_issue_label_strips_leading_zeros():
    assert vc._normalize_issue_label('001') == '1'
    assert vc._normalize_issue_label('01') == '1'
    assert vc._normalize_issue_label('005') == '5'


@pytest.mark.unit
def test_match_issue_id_ignores_filename_year(tmp_path, monkeypatch):
    import mylar
    from mylar import db

    db_path = tmp_path / 'mylar.db'
    conn = __import__('sqlite3').connect(str(db_path))
    conn.execute(
        'CREATE TABLE issues (IssueID TEXT, ComicID TEXT, Issue_Number TEXT, Int_IssueNumber INT)'
    )
    conn.execute("INSERT INTO issues VALUES ('4000-5', '12345', '5', 5000)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(mylar, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(
        vc,
        '_int_issue_number',
        lambda n: {'005': 5000, '5': 5000, '01': 1000}.get(str(n).strip()),
    )

    myDB = db.DBConnection()
    issue_id, issue_number = vc._match_issue_id(myDB, '12345', '005')
    assert issue_id == '4000-5'
    assert issue_number == '5'


@pytest.mark.unit
def test_variant_count_by_comic_groups_by_issue(tmp_path, monkeypatch):
    import mylar
    from mylar import db

    db_path = tmp_path / 'test.db'
    conn = __import__('sqlite3').connect(str(db_path))
    conn.execute(
        'CREATE TABLE variant_covers (VariantID TEXT, ComicID TEXT, IssueID TEXT, '
        'Issue_Number TEXT, Descriptor TEXT, Filename TEXT, Location TEXT, '
        'ComicSize TEXT, CoverOnly INTEGER, ThumbPath TEXT, DateAdded TEXT, DateUpdated TEXT)'
    )
    conn.execute(
        "INSERT INTO variant_covers VALUES ('v1', '99', '4000-1', '1', 'A', 'f1.cbz', '/a', '0', 1, NULL, '', '')"
    )
    conn.execute(
        "INSERT INTO variant_covers VALUES ('v2', '99', '4000-1', '1', 'B', 'f2.cbz', '/b', '0', 1, NULL, '', '')"
    )
    conn.execute(
        "INSERT INTO variant_covers VALUES ('v3', '99', NULL, '2', 'C', 'f3.cbz', '/c', '0', 1, NULL, '', '')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(mylar, 'DB_FILE', str(db_path))
    counts = vc.variant_count_by_comic('99')
    assert counts == {'4000-1': 2}


@pytest.mark.unit
def test_relocate_variant_file_moves_into_subfolder(tmp_path):
    series = tmp_path / 'Elseworlds Finest (1997)'
    series.mkdir()
    src = series / 'Elseworlds Finest 01 (1997) (Variant Cover) (digital).cbz'
    src.write_bytes(b'x')
    dest = vc.relocate_variant_file(str(src), str(series))
    assert dest == str(series / vc.VARIANT_SUBFOLDER_NAME / src.name)
    assert os.path.isfile(dest)
    assert not src.is_file()
    assert vc.relocate_variant_file(dest, str(series)) == dest


@pytest.mark.unit
def test_prune_variant_subdirs_skips_variants_folder():
    subs = ['Variants', 'Annuals', 'variants']
    vc.prune_variant_subdirs(subs)
    assert subs == ['Annuals']


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
