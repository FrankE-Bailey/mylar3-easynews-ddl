# -*- coding: utf-8 -*-
#  This file is part of Mylar.
#
#  Variant cover detection and parsing from filenames / file metadata.

import datetime
import hashlib
import os
import re
import zipfile

# Cover-only variant scans are typically small; full issues are rarely under this size.
DEFAULT_MAX_VARIANT_BYTES = 3 * 1024 * 1024  # 3 MiB
VARIANT_EXTENSIONS = ('.cbr', '.cbz', '.cb7')

VARIANT_EXCLUDE_RE = re.compile(
    r'''(?ix)
    (?:^|[\s\-])(?:the\s+)?variants?\s*[-–]\s|
    \bvariant\s+covers?\s+guide\b|
    \bthe\s+variant\s+covers\b|
    \baction\s+figure\s+variant\s+covers\b|
    \bhip-?hop\s+variant\s+guide\b|
    \bvariant\s+edition\b
    ''',
)

VARIANT_DETECT_RE = re.compile(
    r'''(?ix)
    \(
        (?:
              VC\s*-\s*[^)]+
            | \d+(?:st|nd|rd|th)\s+print(?:ing)?\s+(?:cover|variant)(?:\s+only)?
            | (?:1-in-\d+|I\s*\(\s*\d+\s*\))
            | incentive\s+.+?\s+variant(?:\s+cover)?
            | cover\s+[A-Z](?:\s+[\w.'\u2019-]+){0,4}\s+variant
            | (?:blank|virgin|sketch|foil|lenticular|connecting|nude|adult|spicy)
              (?:\s+[\w.'\u2019-]+){0,4}\s+variant
            | (?:movie|photo)(?:\s+photo)?\s+variant
            | (?:sub(?:scription)?|RI)\s+(?:cover|variant)
            | \d+\s+(?:RI\s+)?covers?\s+only
            | RI\s+cover\s+only
            | variant\s+covers?(?:\s+only|\s+pack)?
            | [^)]{2,120}?\s+variant(?:\s+only)?(?:\s+cover)?
        )
    \)
    |
    (?:
          \b(?:cover|covers)\s+only\b
        | \bvariant\s+cover(?:s)?(?:\s+only|\s+pack)?\b
        | \b\d+(?:st|nd|rd|th)\s+print(?:ing)?\s+(?:cover|variant)\b
        | \b1-in-\d+\b
        | \bVC\s*-\s*\w
        | \b(?:blank|virgin|sketch|foil)\s+(?:cover\s+)?variant\b
        | \b(?:movie|photo)(?:\s+photo)?\s+variant\b
        | \b(?:sub(?:scription)?|RI)\s+variant\b
        | \bTV\s+variant\b
        | \bwith\s+\d+\s+variant\s+covers?\b
        | \b[\w.'\u2019-]+(?:\s+[\w.'\u2019-]+){0,6}\s+variant(?:\s+only)?(?:\s+cover)?\b
    )
    ''',
    re.VERBOSE,
)

VARIANT_DESCRIPTOR_RE = re.compile(
    r'''(?ix)
    \(
        (?P<descriptor>
              VC\s*-\s*(?P<vc_artist>[^)]+)
            | (?P<ratio>1-in-\d+|I\s*\(\s*\d+\s*\))
              (?:\s+(?P<ratio_tail>[^)]+))?
            | (?P<type_variant>(?:blank|virgin|sketch|foil|connecting|movie(?:\s+photo)?|photo)
              (?:\s+[\w.'\u2019-]+){0,4}\s+variant(?:\s+only)?(?:\s+cover)?)
            | cover\s+(?P<cover_letter>[A-Z])(?:\s+(?P<cover_artist>[\w.'\u2019-]+(?:\s+[\w.'\u2019-]+){0,3}))?
              \s+variant
            | (?P<printing>\d+(?:st|nd|rd|th)\s+print(?:ing)?)\s+(?:cover|variant)(?:\s+only)?
            | (?P<artist_variant>[^)]+?\s+variant(?:\s+only)?(?:\s+cover)?)
        )
    \)
    |
    (?P<trailing_artist>[\w.'\u2019-]+(?:\s+[\w.'\u2019-]+){0,6})\s+variant(?:\s+only)?(?:\s+cover)?\b
    |
    (?P<cover_only>\b(?:cover|covers)\s+only\b)
    ''',
    re.VERBOSE,
)

COVER_ONLY_RE = re.compile(
    r'''(?ix)
    \b(?:cover|covers)\s+only\b
    | \bvariant\s+cover(?:s)?\s+only\b
    | \bRI\s+cover\s+only\b
    | \b\d+\s+RI\s+covers?\s+only\b
    ''',
)


def _basename(path_or_name):
    return os.path.basename(path_or_name)


def _stem(path_or_name):
    name = _basename(path_or_name)
    return os.path.splitext(name)[0]


def is_variant_cover_filename(filename):
    """Return True if filename looks like a variant cover (before size check)."""
    stem = _stem(filename)
    if VARIANT_EXCLUDE_RE.search(stem):
        return False
    return bool(VARIANT_DETECT_RE.search(stem))


def is_cover_only_filename(filename):
    stem = _stem(filename)
    return bool(COVER_ONLY_RE.search(stem))


def extract_variant_descriptor(filename):
    """Best-effort variant label from filename for inventory display."""
    stem = _stem(filename)
    m = VARIANT_DESCRIPTOR_RE.search(stem)
    if not m:
        return None
    if m.group('descriptor'):
        return m.group('descriptor').strip()
    if m.group('trailing_artist'):
        return '%s Variant' % m.group('trailing_artist').strip()
    if m.group('cover_only'):
        return 'cover only'
    return None


def file_within_variant_size(path, max_bytes=None):
    if max_bytes is None:
        max_bytes = DEFAULT_MAX_VARIANT_BYTES
    try:
        return os.path.getsize(path) <= max_bytes
    except OSError:
        return False


def classify_variant_file(path, max_bytes=None):
    """
    Classify a file as a variant cover candidate.

    Returns dict with keys:
      is_variant (bool), descriptor (str|None), cover_only (bool),
      size_ok (bool), size_bytes (int|None), filename (str)
    """
    if max_bytes is None:
        max_bytes = DEFAULT_MAX_VARIANT_BYTES
    filename = _basename(path)
    size_bytes = None
    size_ok = False
    try:
        size_bytes = os.path.getsize(path)
        size_ok = size_bytes <= max_bytes
    except OSError:
        pass

    name_match = is_variant_cover_filename(filename)
    result = {
        'filename': filename,
        'path': path,
        'is_variant': bool(name_match and size_ok),
        'name_match': name_match,
        'descriptor': extract_variant_descriptor(filename) if name_match else None,
        'cover_only': is_cover_only_filename(filename) if name_match else False,
        'size_ok': size_ok,
        'size_bytes': size_bytes,
        'max_bytes': max_bytes,
    }
    return result


def scan_paths(paths, max_bytes=None):
    """Yield classify_variant_file() results for paths that pass name + size filters."""
    for path in paths:
        info = classify_variant_file(path, max_bytes=max_bytes)
        if info['is_variant']:
            yield info


def _variant_id_for_path(path):
    return hashlib.md5(os.path.abspath(path).encode('utf-8', errors='replace')).hexdigest()


def _series_scan_paths(comic_row):
    paths = []
    if comic_row.get('ComicLocation') and os.path.isdir(comic_row['ComicLocation']):
        paths.append(comic_row['ComicLocation'])
    try:
        import mylar
        if all([mylar.CONFIG.MULTIPLE_DEST_DIRS, mylar.CONFIG.MULTIPLE_DEST_DIRS != 'None']):
            alt = os.path.join(
                mylar.CONFIG.MULTIPLE_DEST_DIRS,
                os.path.basename(comic_row['ComicLocation']),
            )
            if os.path.isdir(alt):
                paths.append(alt)
            else:
                ff = mylar.filers.FileHandlers(ComicID=comic_row['ComicID'])
                secondary = ff.secondary_folders(comic_row['ComicLocation'])
                if secondary and os.path.isdir(secondary):
                    paths.append(secondary)
    except Exception:
        pass
    return paths


def _match_issue_id(myDB, ComicID, issue_number, issue_year=None):
    from mylar import helpers

    if issue_number in (None, '', 'None'):
        return None, None
    try:
        int_iss = helpers.issuedigits(str(issue_number).strip())
    except Exception:
        return None, str(issue_number)
    rows = myDB.select(
        'SELECT IssueID, Issue_Number, IssueDate FROM issues WHERE ComicID=? AND Int_IssueNumber=?',
        [ComicID, int_iss],
    )
    if not rows:
        return None, str(issue_number)
    if len(rows) == 1:
        return rows[0]['IssueID'], rows[0]['Issue_Number']
    if issue_year:
        for row in rows:
            if row.get('IssueDate') and str(issue_year) in row['IssueDate'][:4]:
                return row['IssueID'], row['Issue_Number']
    return rows[0]['IssueID'], rows[0]['Issue_Number']


def _first_image_from_cbz(path):
    try:
        with zipfile.ZipFile(path, mode='r') as zf:
            names = [
                n for n in zf.namelist()
                if n.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))
                and not n.startswith('__MACOSX')
            ]
            if not names:
                return None
            names.sort()
            return zf.read(names[0])
    except Exception:
        return None


def ensure_variant_thumbnail(path, variant_id=None, cache_dir=None):
    """Cache first page image for a variant archive; returns cache file path or None."""
    import mylar
    from mylar import logger

    if cache_dir is None:
        cache_dir = os.path.join(mylar.CONFIG.CACHE_DIR, 'variant_covers')
    os.makedirs(cache_dir, exist_ok=True)
    if variant_id is None:
        variant_id = _variant_id_for_path(path)
    thumb_path = os.path.join(cache_dir, '%s.jpg' % variant_id)
    if os.path.exists(thumb_path):
        return thumb_path
    if not path.lower().endswith('.cbz'):
        return None
    image_data = _first_image_from_cbz(path)
    if not image_data:
        return None
    try:
        with open(thumb_path, 'wb') as fh:
            fh.write(image_data)
        return thumb_path
    except Exception as err:
        logger.fdebug('[VARIANT-COVERS] thumbnail write failed for %s: %s' % (path, err))
        return None


def scan_series_variant_covers(ComicID, paths=None, max_bytes=None):
    """
    Scan series folder(s) for variant cover files and upsert into variant_covers.
  Qualified files must match variant filename patterns and be <= max_bytes (default 3MB).
    """
    from mylar import db, filechecker, helpers, logger

    myDB = db.DBConnection()
    comic = myDB.selectone('SELECT * FROM comics WHERE ComicID=?', [ComicID]).fetchone()
    if comic is None:
        return 0
    if paths is None:
        paths = _series_scan_paths(dict(comic))
    if not paths:
        return 0

    if max_bytes is None:
        max_bytes = DEFAULT_MAX_VARIANT_BYTES

    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    found_locations = []
    count = 0

    for rootpath in paths:
        for r, _d, files in os.walk(rootpath):
            for fn in files:
                if not fn.lower().endswith(VARIANT_EXTENSIONS):
                    continue
                full = os.path.join(r, fn)
                info = classify_variant_file(full, max_bytes=max_bytes)
                if not info['is_variant']:
                    continue
                found_locations.append(full)
                variant_id = _variant_id_for_path(full)

                fc = filechecker.FileChecker(file=fn, justparse=True, manual=True)
                parsed = fc.parseit(path=r, filename=fn) or {}
                issue_id, issue_number = _match_issue_id(
                    myDB,
                    ComicID,
                    parsed.get('issue_number'),
                    parsed.get('issue_year'),
                )
                thumb_path = ensure_variant_thumbnail(full, variant_id=variant_id)

                value_dict = {
                    'VariantID': variant_id,
                    'ComicID': ComicID,
                    'IssueID': issue_id,
                    'Issue_Number': issue_number or parsed.get('issue_number'),
                    'Descriptor': info['descriptor'] or 'variant',
                    'Filename': fn,
                    'Location': full,
                    'ComicSize': str(info['size_bytes'] or 0),
                    'CoverOnly': 1,
                    'ThumbPath': thumb_path,
                    'DateUpdated': now,
                }
                existing = myDB.selectone(
                    'SELECT VariantID, DateAdded FROM variant_covers WHERE Location=?',
                    [full],
                ).fetchone()
                if existing:
                    value_dict.pop('VariantID', None)
                    if not value_dict.get('ThumbPath'):
                        value_dict.pop('ThumbPath', None)
                    myDB.upsert('variant_covers', value_dict, {'Location': full})
                else:
                    value_dict['DateAdded'] = now
                    myDB.upsert('variant_covers', value_dict, {'VariantID': variant_id})

                count += 1

    stale = myDB.select('SELECT VariantID, Location FROM variant_covers WHERE ComicID=?', [ComicID])
    for row in stale:
        if row['Location'] not in found_locations:
            myDB.action('DELETE FROM variant_covers WHERE VariantID=?', [row['VariantID']])

    logger.info(
        '[VARIANT-COVERS] Catalogued %s variant cover(s) for %s'
        % (count, comic['ComicName'])
    )
    return count


def get_series_variants(ComicID):
    from mylar import db

    myDB = db.DBConnection()
    return myDB.select(
        'SELECT * FROM variant_covers WHERE ComicID=? ORDER BY Issue_Number ASC, Descriptor ASC',
        [ComicID],
    )

