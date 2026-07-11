# -*- coding: utf-8 -*-
#  This file is part of Mylar.
#
#  Variant cover detection and parsing from filenames / file metadata.

import datetime
import hashlib
import os
import re
import shutil
import zipfile
from io import BytesIO

# Cover-only variant scans are typically small; full issues are rarely under this size.
DEFAULT_MAX_VARIANT_BYTES = 13 * 1024 * 1024  # 13 MiB
VARIANT_SUBFOLDER_NAME = 'Variants'
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


def _variant_id_for_entry(ComicID, filename):
    key = '%s|%s' % (ComicID, filename)
    return hashlib.md5(key.encode('utf-8', errors='replace')).hexdigest()


def is_variant_subfolder_name(name):
    return (name or '').lower() == VARIANT_SUBFOLDER_NAME.lower()


def prune_variant_subdirs(dirnames):
    """Remove Variants from os.walk descent so issue scans skip variant storage."""
    dirnames[:] = [d for d in dirnames if not is_variant_subfolder_name(d)]


def _variant_subfolder(series_root):
    return os.path.join(series_root, VARIANT_SUBFOLDER_NAME)


def _is_in_variant_subfolder(path, series_root):
    try:
        rel = os.path.relpath(os.path.dirname(os.path.abspath(path)), os.path.abspath(series_root))
    except ValueError:
        return False
    if rel in ('.', ''):
        return False
    return rel.split(os.sep)[0].lower() == VARIANT_SUBFOLDER_NAME.lower()


def relocate_variant_file(path, series_root):
    """Move a variant cover into series_root/Variants/ if it is not already there."""
    from mylar import logger

    if _is_in_variant_subfolder(path, series_root):
        return path
    dest_dir = _variant_subfolder(series_root)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(path))
    if os.path.abspath(path) == os.path.abspath(dest):
        return path
    if os.path.exists(dest):
        if os.path.abspath(path) != os.path.abspath(dest):
            try:
                os.remove(path)
                logger.info(
                    '[VARIANT-COVERS] Removed duplicate at series root (already in %s): %s'
                    % (VARIANT_SUBFOLDER_NAME, os.path.basename(path))
                )
            except Exception as err:
                logger.warn(
                    '[VARIANT-COVERS] Already exists in %s, leaving source in place: %s (%s)'
                    % (VARIANT_SUBFOLDER_NAME, path, err)
                )
        return dest
    try:
        shutil.move(path, dest)
        logger.info('[VARIANT-COVERS] Moved to %s: %s' % (VARIANT_SUBFOLDER_NAME, os.path.basename(dest)))
        return dest
    except Exception as err:
        logger.warn('[VARIANT-COVERS] Move failed for %s: %s' % (path, err))
        return path


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


def _int_issue_number(issue_number):
    from mylar import helpers

    try:
        return helpers.issue_number_parser(str(issue_number).strip()).asInt
    except Exception:
        return None


def _normalize_issue_label(value):
    if value in (None, '', 'None'):
        return None
    s = str(value).strip()
    if re.match(r'^\d+$', s):
        return str(int(s))
    return s.lower()


def _extract_issue_number_from_filename(filename):
    """Best-effort issue number when filechecker parseit does not return one."""
    base = os.path.splitext(filename)[0]
    for pattern in (
        r'(\d{1,4})\s*\(\d{4}\)',           # 001 (2021)
        r'(\d{1,4})\s*\([^)]*variant',     # 001 (Blank Variant
        r'(\d{1,4})\s*\(of\s+\d+',          # 01 (of 08
    ):
        match = re.search(pattern, base, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _match_issue_id(myDB, ComicID, issue_number, issue_year=None):
    """Match a variant file to a series issue by issue number only (year ignored)."""
    if issue_number in (None, '', 'None'):
        return None, None

    int_iss = _int_issue_number(issue_number)
    if int_iss is not None:
        rows = myDB.select(
            'SELECT IssueID, Issue_Number FROM issues WHERE ComicID=? AND Int_IssueNumber=?',
            [ComicID, int_iss],
        )
        if rows:
            return rows[0]['IssueID'], rows[0]['Issue_Number']
        rows = myDB.select(
            'SELECT IssueID, Issue_Number FROM annuals '
            'WHERE ComicID=? AND Int_IssueNumber=? AND NOT Deleted',
            [ComicID, int_iss],
        )
        if rows:
            return rows[0]['IssueID'], rows[0]['Issue_Number']

    target = _normalize_issue_label(issue_number)
    if target:
        for row in myDB.select('SELECT IssueID, Issue_Number FROM issues WHERE ComicID=?', [ComicID]):
            if _normalize_issue_label(row['Issue_Number']) == target:
                return row['IssueID'], row['Issue_Number']
        for row in myDB.select(
            'SELECT IssueID, Issue_Number FROM annuals WHERE ComicID=? AND NOT Deleted',
            [ComicID],
        ):
            if _normalize_issue_label(row['Issue_Number']) == target:
                return row['IssueID'], row['Issue_Number']

    return None, str(issue_number)


def _image_entries_from_cbz(path):
    """Return sorted list of (zip_member_name,) for image files inside a CBZ."""
    try:
        with zipfile.ZipFile(path, mode='r') as zf:
            names = [
                n for n in zf.namelist()
                if n.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))
                and not n.startswith('__MACOSX')
                and not n.endswith('/')
            ]
            return sorted(names)
    except Exception:
        return []


def _pick_cover_member(members):
    if not members:
        return None
    if len(members) == 1:
        return members[0]
    for name in members:
        base = os.path.basename(name).lower()
        if 'cover' in base:
            return name
    for name in members:
        base = os.path.basename(name).lower()
        if base in ('00.jpg', '00.png', '01.jpg', '01.png', '001.jpg', '001.png'):
            return name
    return members[0]


def _read_zip_member(path, member):
    with zipfile.ZipFile(path, mode='r') as zf:
        return zf.read(member)


def _cover_image_bytes_from_cbz(path):
    """Extract raw image bytes for the cover page from a CBZ (full resolution)."""
    from mylar import getimage, logger

    members = _image_entries_from_cbz(path)
    member = _pick_cover_member(members)
    if member:
        try:
            return _read_zip_member(path, member)
        except Exception as err:
            logger.fdebug('[VARIANT-COVERS] zip read failed for %s: %s' % (path, err))

    try:
        result = getimage.extract_image(path, single=True)
        if result and result.get('rawImage'):
            return result['rawImage']
    except Exception as err:
        logger.fdebug('[VARIANT-COVERS] getimage cover extract failed for %s: %s' % (path, err))
    return None


def _encode_variant_jpeg(image_bytes, max_width=None):
    """Normalize cover bytes to JPEG for browser display."""
    from mylar import getimage, logger

    if not image_bytes:
        return None
    try:
        from PIL import Image
    except Exception:
        logger.warn('[VARIANT-COVERS] PIL unavailable; cannot render variant cover images')
        return image_bytes if image_bytes[:3] == b'\xff\xd8\xff' else None

    try:
        img = Image.open(BytesIO(image_bytes))
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        if max_width and img.size[0] > max_width:
            if getimage.PIL_Found:
                data = getimage.scale_image(img, 'JPEG', max_width)
            else:
                scale = max_width / float(img.size[0])
                new_size = (max_width, int(scale * img.size[1]))
                img = img.resize(new_size, Image.LANCZOS)
                buf = BytesIO()
                img.save(buf, format='JPEG', quality=88)
                data = buf.getvalue()
            return data
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=92)
        return buf.getvalue()
    except Exception as err:
        logger.fdebug('[VARIANT-COVERS] JPEG encode failed: %s' % err)
        return None


def _first_image_from_cbz(path):
    return _cover_image_bytes_from_cbz(path)


def resolve_variant_location(location, comic_location=None, filename=None):
    """Return an on-disk path for a catalogued variant, including Variants/ fallback."""
    if location and os.path.isfile(location):
        return location
    fn = filename or (os.path.basename(location) if location else None)
    if not fn:
        return None
    candidates = []
    if location:
        dirname = os.path.dirname(location)
        candidates.append(os.path.join(dirname, VARIANT_SUBFOLDER_NAME, fn))
        if os.path.basename(dirname).lower() != VARIANT_SUBFOLDER_NAME.lower():
            parent = os.path.dirname(dirname)
            if parent:
                candidates.append(os.path.join(parent, VARIANT_SUBFOLDER_NAME, fn))
    if comic_location:
        candidates.append(os.path.join(comic_location, VARIANT_SUBFOLDER_NAME, fn))
        candidates.append(os.path.join(comic_location, fn))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def variant_cover_cache_url(path, cache_root=None):
    """Map an absolute cache file path to a browser URL under /cache/."""
    if not path or not os.path.isfile(path):
        return None
    if cache_root is None:
        import mylar
        cache_root = mylar.CONFIG.CACHE_DIR
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(cache_root))
    except ValueError:
        return None
    rel = rel.replace('\\', '/')
    if rel.startswith('..'):
        return None
    return 'cache/' + rel


def _variant_cache_paths(variant_id, cache_dir=None):
    import mylar

    if cache_dir is None:
        cache_dir = os.path.join(mylar.CONFIG.CACHE_DIR, 'variant_covers')
    os.makedirs(cache_dir, exist_ok=True)
    thumb_path = os.path.join(cache_dir, '%s_thumb.jpg' % variant_id)
    full_path = os.path.join(cache_dir, '%s_full.jpg' % variant_id)
    return cache_dir, thumb_path, full_path


def read_variant_cover_jpeg(path, variant_id=None, max_width=None, cache_dir=None):
    """
    Return JPEG bytes for a variant archive cover.
    max_width=None returns full-resolution JPEG; otherwise scales down for thumbnails.
    """
    if not path or not os.path.isfile(path) or not path.lower().endswith('.cbz'):
        return None
    if variant_id:
        import mylar
        if cache_dir is None:
            cache_dir = os.path.join(mylar.CONFIG.CACHE_DIR, 'variant_covers')
        _, thumb_path, full_path = _variant_cache_paths(variant_id, cache_dir=cache_dir)
        cache_path = thumb_path if max_width else full_path
        src_mtime = os.path.getmtime(path)
        if os.path.isfile(cache_path) and os.path.getmtime(cache_path) >= src_mtime:
            try:
                with open(cache_path, 'rb') as fh:
                    return fh.read()
            except Exception:
                pass
    raw = _cover_image_bytes_from_cbz(path)
    jpeg = _encode_variant_jpeg(raw, max_width=max_width)
    if jpeg and variant_id:
        if cache_dir is None:
            import mylar
            cache_dir = os.path.join(mylar.CONFIG.CACHE_DIR, 'variant_covers')
        _, thumb_path, full_path = _variant_cache_paths(variant_id, cache_dir=cache_dir)
        cache_path = thumb_path if max_width else full_path
        try:
            with open(cache_path, 'wb') as fh:
                fh.write(jpeg)
        except Exception:
            pass
    return jpeg


def ensure_variant_thumbnail(path, variant_id=None, cache_dir=None):
    """Cache thumbnail JPEG for a variant archive; returns cache file path or None."""
    import mylar
    from mylar import logger

    if cache_dir is None:
        cache_dir = os.path.join(mylar.CONFIG.CACHE_DIR, 'variant_covers')
    if variant_id is None:
        variant_id = _variant_id_for_path(path)
    _, thumb_path, _ = _variant_cache_paths(variant_id, cache_dir=cache_dir)
    if not path.lower().endswith('.cbz'):
        return None
    jpeg = read_variant_cover_jpeg(path, variant_id=variant_id, max_width=600, cache_dir=cache_dir)
    if not jpeg:
        logger.fdebug('[VARIANT-COVERS] no cover image in %s' % path)
        return None
    if not os.path.isfile(thumb_path):
        try:
            with open(thumb_path, 'wb') as fh:
                fh.write(jpeg)
        except Exception as err:
            logger.fdebug('[VARIANT-COVERS] thumbnail write failed for %s: %s' % (path, err))
            return None
    return thumb_path


def scan_series_variant_covers(ComicID, paths=None, max_bytes=None):
    """
    Scan series folder(s) for variant cover files and upsert into variant_covers.
    Qualified files must match variant filename patterns and be <= max_bytes (default 13MB).
    Matching files are moved into a Variants/ subfolder under each series root.
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
    seen_variant_ids = set()
    count = 0

    for rootpath in paths:
        for r, _dirnames, files in os.walk(rootpath):
            for fn in files:
                if not fn.lower().endswith(VARIANT_EXTENSIONS):
                    continue
                full = os.path.join(r, fn)
                info = classify_variant_file(full, max_bytes=max_bytes)
                if not info['is_variant']:
                    continue
                full = relocate_variant_file(full, rootpath)
                info = classify_variant_file(full, max_bytes=max_bytes)
                if not info['is_variant']:
                    continue
                variant_id = _variant_id_for_entry(ComicID, fn)
                if variant_id in seen_variant_ids:
                    continue
                seen_variant_ids.add(variant_id)
                found_locations.append(full)

                fc = filechecker.FileChecker(file=fn, justparse=True, manual=True)
                parsed = fc.parseit(path=os.path.dirname(full), filename=fn) or {}
                parsed_issue = parsed.get('issue_number') or _extract_issue_number_from_filename(fn)
                issue_id, issue_number = _match_issue_id(
                    myDB,
                    ComicID,
                    parsed_issue,
                )
                thumb_path = None
                try:
                    thumb_path = ensure_variant_thumbnail(full, variant_id=variant_id)
                except Exception as err:
                    logger.fdebug('[VARIANT-COVERS] thumbnail skipped for %s: %s' % (full, err))

                value_dict = {
                    'VariantID': variant_id,
                    'ComicID': ComicID,
                    'IssueID': issue_id,
                    'Issue_Number': issue_number or parsed_issue or parsed.get('issue_number'),
                    'Descriptor': info['descriptor'] or 'variant',
                    'Filename': fn,
                    'Location': full,
                    'ComicSize': str(info['size_bytes'] or 0),
                    'CoverOnly': 1,
                    'ThumbPath': thumb_path,
                    'DateUpdated': now,
                }
                existing = myDB.selectone(
                    'SELECT VariantID, DateAdded, Location FROM variant_covers WHERE VariantID=? OR Location=?',
                    [variant_id, full],
                ).fetchone()
                if existing:
                    value_dict.pop('VariantID', None)
                    if not value_dict.get('ThumbPath'):
                        value_dict.pop('ThumbPath', None)
                    if existing['Location'] != full:
                        myDB.action('DELETE FROM variant_covers WHERE VariantID=?', [existing['VariantID']])
                        value_dict['VariantID'] = variant_id
                        value_dict['DateAdded'] = existing.get('DateAdded') or now
                        myDB.upsert('variant_covers', value_dict, {'VariantID': variant_id})
                    else:
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


def build_variant_payload(row, comic_loc=None, myDB=None):
    """Serialize a variant_covers row for the UI, resolving paths and cache URLs."""
    from mylar import db

    r = dict(row)
    if myDB is None:
        myDB = db.DBConnection()
    loc = resolve_variant_location(
        r.get('Location'),
        comic_location=comic_loc,
        filename=r.get('Filename'),
    )
    vid = r.get('VariantID')
    thumb_url = None
    image_url = None
    if loc and loc.lower().endswith('.cbz'):
        if loc != r.get('Location'):
            myDB.upsert('variant_covers', {'Location': loc}, {'VariantID': vid})
        read_variant_cover_jpeg(loc, variant_id=vid, max_width=600)
        read_variant_cover_jpeg(loc, variant_id=vid, max_width=None)
        _, thumb_path, full_path = _variant_cache_paths(vid)
        thumb_url = variant_cover_cache_url(thumb_path)
        image_url = variant_cover_cache_url(full_path)
        if thumb_path:
            myDB.upsert('variant_covers', {'ThumbPath': thumb_path}, {'VariantID': vid})
    return {
        'VariantID': vid,
        'IssueID': r.get('IssueID'),
        'Issue_Number': r.get('Issue_Number') or '',
        'Descriptor': r.get('Descriptor') or '',
        'Filename': r.get('Filename') or '',
        'ComicSize': r.get('ComicSize') or '',
        'CoverOnly': r.get('CoverOnly'),
        'thumb_url': thumb_url,
        'image_url': image_url,
    }


def variant_count_by_comic(ComicID):
    from mylar import db

    myDB = db.DBConnection()
    rows = myDB.select(
        'SELECT IssueID, COUNT(*) AS cnt FROM variant_covers '
        'WHERE ComicID=? AND IssueID IS NOT NULL GROUP BY IssueID',
        [ComicID],
    )
    return {row['IssueID']: row['cnt'] for row in rows}


def get_variants_for_issue(IssueID, comic_loc=None):
    from mylar import db

    myDB = db.DBConnection()
    rows = myDB.select(
        'SELECT * FROM variant_covers WHERE IssueID=? ORDER BY Descriptor ASC',
        [IssueID],
    )
    return [build_variant_payload(row, comic_loc=comic_loc, myDB=myDB) for row in rows]


def get_series_variants(ComicID):
    from mylar import db

    myDB = db.DBConnection()
    return myDB.select(
        'SELECT * FROM variant_covers WHERE ComicID=? ORDER BY Issue_Number ASC, Descriptor ASC',
        [ComicID],
    )

