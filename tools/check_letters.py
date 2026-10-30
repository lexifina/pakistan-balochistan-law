"""Independent letters-and-digits check of a Balochistan part against the source PDFs, read by a second engine (xpdf
pdftotext -raw), adapted from scripts/india-maharashtra-law/check_letters.py (private).

    python -X utf8 check_letters.py corpus.d/20-acts-01.json [...]

For each Act, its units (heading lines left out) reduced to letters and digits must be found, in order, in the PDF's
text reduced the same way. Source text may be passed over only where it cannot be part of the body: up to four digits
(footnote numbers) inside the body; a stretch that crosses exactly one page break (running head, footnotes, page
number); or, within a page, a stretch made up only of running heads, marginal notes (section headings printed in the margin) and footnote texts (the two engines order such
text differently). Anything else is a mismatch.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FF = '\x0c'


def ld(s):
    return ''.join(ch for ch in s if ch.isalnum() or ch == FF)


def source(pdf):
    out = subprocess.run(['pdftotext', '-raw', '-enc', 'UTF-8', str(pdf), '-'], capture_output=True).stdout
    return ld(out.decode('utf-8', 'replace'))


def pat(s):
    return re.compile(r'\d{0,3}'.join(map(re.escape, s)))


def align(U, S, body_at=0, aside=()):
    """body_at: where in U the first section starts. The record starts at the Act's title page, which is the last
    place its opening words occur before the first section's words (the cover and contents repeat the title).
    aside: the letters and digits of each line the parser left out of the text, longest first."""
    # The first section's words can also stand in the table of contents (a modern Act prints "1. Short title,
    # extent and commencement" there and as the section's own heading), so the title page is looked for before each
    # of their first four occurrences in turn (2026-10-31); the walk and what it may pass over are the same each time.
    limits = [x.start() for x, _ in zip(pat(U[body_at:body_at + 30]).finditer(S), range(4))] or [len(S)]
    res = None
    for limit in limits:
        r = _align_from(U, S, limit, aside)
        if r[0]:
            return r[:2]
        if res is None or r[2] > res[2]:
            res = r   # report the attempt that matched the most of the record
    return res[:2]


def _align_from(U, S, limit, aside=()):
    i = j = 0
    first = None
    skips = 0
    for n in (40, 16):
        p = [x.start() for x in pat(U[:n]).finditer(S, 0, limit)]
        if p:
            j = first = p[-1]
            break
    while i < len(U):
        if j < len(S) and S[j] == U[i]:
            if first is None:
                first = j
            i += 1; j += 1
            continue
        hit = None
        for L in (1, 2, 3, 4):
            if j + L <= len(S) and S[j:j + L].isdigit() and S[j + L:j + L + 8] == U[i:i + 8]:
                hit = j + L; break
        if hit is not None:
            j = hit; skips += 1
            continue
        # the next 16 characters of the record, footnote numbers (up to 3 digits) allowed between them in the source
        m = re.compile(r'\d{0,3}'.join(map(re.escape, U[i:i + 16]))).search(S, j)
        pos = m.start() if m else -1
        if pos < 0:
            return False, f'record text not found in the PDF from here: {U[i:i + 60]!r}', i
        gap = S[j:pos]
        if passable(gap, first, aside):
            j = pos; skips += 1
            continue
        # The same rule, other alignments (2026-10-31): the greedy walk can pair the record's next letters with the
        # wrong occurrence (the "Pr" of a margin note "Preservation ..." for the "Pr" of "Provided", or the "7" of a
        # running head's "1975" for section "7A"), so that the stretch passed over is no longer exactly set-aside
        # text. Try the record's last few matched letters re-paired later (back <= 12) and the later occurrences of
        # its next 16 letters within this page; a stretch is still passed over only under passable(), unchanged.
        found = None
        # only within this page and the next (a stretch over more pages is not passable here anyway)
        f1 = S.find(FF, j)
        end = len(S) if f1 < 0 else (S.find(FF, f1 + 1) if S.find(FF, f1 + 1) >= 0 else len(S))
        for b in range(0, 13):
            if b and (i - b < 0 or j - b < 0 or U[i - b:i] != S[j - b:j]):
                break
            p16 = re.compile(r'\d{0,3}'.join(map(re.escape, U[i - b:i - b + 16])))
            at = j - b + (1 if b else 0)
            for _ in range(12):
                m2 = p16.search(S, at, end)
                if not m2 or FF in S[j - b:m2.start()] and S[j - b:m2.start()].count(FF) > 1:
                    break
                if (b or m2.start() != pos) and passable(S[j - b:m2.start()], first, aside):
                    found = (i - b, m2.start())
                    break
                at = m2.start() + 1
            if found:
                break
        if found:
            i, j = found; skips += 1
            continue
        return False, f'source passed over within a page ({len(gap)} chars): {gap[:80]!r} before {U[i:i + 40]!r}', i
    return True, f'{len(U)} chars matched, {skips} skips', i


def passable(gap, first, aside):
    """What may be passed over in the source (the rule above, unchanged): a stretch before the record starts, one
    crossing exactly one page break, page breaks only, a footnote number, within a page only text the parser set
    aside (plus up to four digits), or several page breaks over pages empty of letters."""
    if (first is None or gap.count(FF) == 1 or (gap.count(FF) > 1 and not gap.replace(FF, ''))
            or (len(gap) <= 4 and gap.isdigit())):
        return True
    if aside and FF not in gap:
        rest = gap.lower()
        for a in aside:
            if a in rest:
                rest = rest.replace(a, '', 1)
        if len(rest) <= 4 and (not rest or rest.isdigit()):
            return True
    if gap.count(FF) > 1 and first is not None:
        inner = gap.split(FF)[1:-1]
        if all(len(p) < 40 for p in inner):
            return True
    return False


def aside_of(pdf, parsed=None):
    """The letters and digits of the running heads and footnotes parse.py set aside (its layout rules, not its text).
    Matched case-blind (running heads come back lower-cased from parse.heads())."""
    import parse
    r = parsed or parse.parse(pdf)
    out = set()
    for h in r['heads']:
        out.add(h)
    for a in r.get('aside', []):
        out.add(ld(a).lower())
    for n in r['notes']:
        out.add(ld(n['text']).lower())
    return sorted((a for a in out if len(a) >= 3), key=lambda a: (-len(a), a))


def check_act(units, S, aside=()):
    U, body_at = '', 0
    for k, u in units.items():
        if k.startswith('sec-') and not body_at:
            body_at = len(U)
        U += ld(re.sub(r'(?m)^# .*$', '', u['text']))
    return align(U, S, body_at, aside)


def pdf_of(url):
    sys.path.insert(0, str(HERE.parent / 'world-law'))
    import pkmy_fetch
    return pkmy_fetch.path_for(url)


def main(paths):
    bad = total = 0
    for p in paths:
        c = json.load(open(p, encoding='utf-8'))
        side = Path(p).with_name(Path(p).stem + '.parser.txt')
        parsers = json.load(open(side, encoding='utf-8')) if side.exists() else {}
        for a in c['acts']:
            v = a['versions'][-1]
            pdf = Path(a['_pdf']) if a.get('_pdf') else pdf_of(v['source_url'])
            S = source(pdf)
            # the reader variant that made this act's text (corpus.d/<part>.parser.txt) says which lines are set aside
            import parse as _p
            ok, msg = check_act(v['units'], S, aside_of(pdf, _p.parse(pdf, tables=parsers.get(a['slug']) == 'tables')))
            total += 1
            if not ok:
                bad += 1
                print(f'MISMATCH {a["slug"]}: {msg}')
    print(f'{total} acts checked, {bad} mismatches')
    return bad


if __name__ == '__main__':
    sys.exit(1 if main(sys.argv[1:] or sorted(str(p) for p in (HERE / 'corpus.d').glob('*.json'))) else 0)
