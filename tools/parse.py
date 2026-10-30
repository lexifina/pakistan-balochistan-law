"""Balochistan Code PDF -> units (private). The Law Department's PDFs (Word or OpenOffice made) print each section's
heading as a marginal note on the left, the section number in its own column and the text to its right; footnotes
in small type at the foot of the page; the title and Act number at the head of the first page.

    python -X utf8 parse.py <pdf>     # print the units

Rules:
- body size = the most common font size (by characters); rows of smaller type at the foot of a page are footnotes
  (returned separately); digit-only spans in small type inside a body row are footnote markers (dropped);
- the section column is where the "N." rows start; lines lying wholly left of it are marginal notes (left out, like
  the section headings printed in the margin of the reprints) and are returned for the independent check;
- rows are the lines of one baseline, left to right; a paragraph starts on a row that opens with a section number
  in sequence, a label "(1)", "(a)", "(i)", a Schedule or a centred heading; other rows continue the paragraph;
- the table of contents (from "CONTENTS" to the title printed again) is left out.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf

LABEL = re.compile(r'^(\(|\[)?\(?([a-z]{1,3}|[0-9]{1,3}[A-Z]?|[ivxlc]{1,6}|[A-Z])\)')
SECNO = re.compile(r'^\[?(\d{1,3})([A-Z]{0,2})\s?\.(?=\s|$|[\[(“"A-Z—–-])')
SCHED = re.compile(r'^\[?(THE\s+)?((FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH)\s+)?'
                   r'(SCHEDULE|ANNEX(URE)?|APPENDIX|FORM)\b', re.I)
CONTENTS = re.compile(r'^\s*C\s*O\s*N\s*T\s*E\s*N\s*T\s*S\s*$', re.I)
NEWPARA = re.compile(r'^(Provided|Explanation|Illustration|An\s+(Act|Ordinance)|AN\s+(ACT|ORDINANCE)|WHEREAS|It\s+is\s+hereby|'
                     r'\[\d{1,2}(st|nd|rd|th)\s|\((Baln|Balochistan|Bal)\.?\s+(Act|Ordinance|Regulation))', re.I)
INCONTENTS = re.compile(r'\bCONTENTS\b')
BODYSTART = re.compile(r'^(\(?(THE\s+)?(BALOCHISTAN|BALN|BAL)\b.*\b(ACT|ORDINANCE|REGULATIONS?)\b|AN\s+(ACT|ORDINANCE)\b|'
                       r'\[?THE\s.*\b(ACT|ORDINANCE|REGULATIONS?),?\s*\d{4}\b|'
                       r'WHEREAS\b|\[\d{1,2}(st|nd|rd|th)\s)', re.I)
# a section number printed without its full stop, directly before its first subsection ("[11    (1) No place ...");
# taken only as the next section in sequence
SECNO_BARE = re.compile(r'^\[?(\d{1,3})([A-Z]{0,2})\s+(?=\(1\)\s)')
PAGENO = re.compile(r'^\s*(-\s*)?\d{1,4}(\s*-)?\s*$|^\s*Page\s*\d+(\s*of\s*\d+)?\s*$|^\s*\(?\d{1,4}\)?\s*\|\s*P\s*a\s*g\s*e\s*$', re.I)


DESIG = re.compile(r'^(Vice[- ]?|Co-?)?(Chair(man|person)?|Members?|Secretary|Convener|President)'
                   r'([- ]+(cum[- ]+)?(Secretary|Member|Chair(man|person)))?\s*[.;,:]?$', re.I)
PARTIAL = re.compile(r'^(Vice|Co-?|Member[- ]cum[- ]?|Chair(man|person)[- ]cum[- ]?)$', re.I)


# "4 | P a g e THE ... ACT, 2024": a page number printed on the running head's own line
PAGEPFX = re.compile(r'^\s*\(?\d{1,4}\)?\s*\|\s*P\s*a\s*g\s*e\s*', re.I)


def headkey(t: str) -> str:
    return ld(PAGEPFX.sub('', t))


def ld(s: str) -> str:
    return ''.join(ch for ch in s if ch.isalnum()).lower()


def norm(s: str) -> str:
    s = s.replace('\xa0', ' ').replace('­', '').replace('﻿', '')
    return re.sub(r'\s+', ' ', s).strip()


def right_cells(pdf: Path) -> list[list[tuple[str, str]]]:
    """Designations printed alone in a right-hand table column beside a left cell (the "Chairperson" / "Member"
    column of a Board's membership table). The Pakistan Code parser joins each one into the left cell's row it sits
    beside; the printed order is the left cell, then the right cell. Returns, per cell, its lines as (the tail of the
    left-hand text on the same row, the cell line); a cell may take two lines ("Vice" / "Chairperson")."""
    doc = pymupdf.open(str(pdf))
    out = []
    for page in doc:
        W = page.rect.width
        lines = []
        for b in page.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                t = re.sub(r'\s+', ' ', ''.join(s['text'] for s in l['spans'])).strip()
                if t:
                    lines.append((l['bbox'], t))
        prev = None
        for (x0, y0, x1, y1), t in sorted(lines, key=lambda z: (z[0][1], z[0][0])):
            if x0 < 0.5 * W or len(t.split()) > 4 or not (DESIG.match(t) or PARTIAL.match(t)):
                continue
            left = [(bx1, tt) for (bx0, by0, bx1, by1), tt in lines if bx1 < x0 - 15 and by0 < y1 - 2 and by1 > y0 + 2]
            if not left:
                continue
            tail = max(left)[1][-25:]
            if prev and PARTIAL.match(prev[-1][1]) and y0 - prev_y1 < 1.6 * (y1 - y0):
                prev.append((tail, t))
            else:
                prev = [(tail, t)]
                out.append(prev)
            prev_y1 = y1
    return [c for c in out if DESIG.match(' '.join(x[1] for x in c).replace('- ', '-'))]


def move_cells(line: str, cells: list) -> str:
    """'(a) Secretary ..., Commerce Chairperson and Technical Education Department;' ->
    '(a) Secretary ..., Commerce and Technical Education Department; Chairperson' (a labelled table row only, and
    only where the designation follows the very words printed beside it)."""
    if not re.match(r'^(\(?[a-z0-9ivx]{1,4}\)|\d{1,2}\.\s)', line):
        return line
    for cell in cells:
        t = line
        ok = True
        for tail, part in cell:
            k = t.find(tail + ' ' + part)
            if k < 0 or k + len(tail) + 1 + len(part) >= len(t.rstrip()):
                ok = False
                break
            t = t[:k + len(tail)] + t[k + len(tail) + 1 + len(part):]
        if ok:
            return t.rstrip() + ' ' + ' '.join(p for _, p in cell).replace('- ', '-')
    return line


def table_rows(doc, raw: list, body: float) -> list:
    """Ruled tables (PyMuPDF's table finder; two or more rows and columns): their lines are replaced by one row per
    table row, each cell's lines in reading order, cells left to right. That is the order the PDF holds a Word table
    in, which pdftotext -raw follows; reading the table line by line across the page interleaves the cells
    (2026-10-31). A table any of whose lines falls outside every cell is left as it was."""
    out = list(raw)
    for pno, page in enumerate(doc):
        try:
            # line-based (ruled) tables only: use_layout=False keeps PyMuPDF's neural layout model (onnxruntime,
            # many threads) out of it
            tabs = page.find_tables(use_layout=False).tables
        except Exception:  # noqa: BLE001
            continue
        for t in tabs:
            if t.row_count < 2 or t.col_count < 2:
                continue
            last = [r[-1] for r in t.extract() if r and r[-1]]
            if last and all(DESIG.match(norm(c.replace(chr(10), ' '))) or PARTIAL.match(norm(c.replace(chr(10), ' ')))
                            for c in last):
                continue  # a membership table (designations in its last column): the designation-cell rule reads it
            X0, Y0, X1, Y1 = t.bbox
            inside = [r for r in out if r[0] == pno and len(r) == 8 and X0 - 1 <= (r[1] + r[3]) / 2 <= X1 + 1
                      and Y0 - 1 <= (r[2] + r[4]) / 2 <= Y1 + 1]
            if not inside:
                continue
            grid: dict = {}
            ok = True
            for r in inside:
                cx, cy = (r[1] + r[3]) / 2, (r[2] + r[4]) / 2
                hit = None
                for ri, row in enumerate(t.rows):
                    for ci, c in enumerate(row.cells):
                        if c and c[0] - 1 <= cx <= c[2] + 1 and c[1] - 1 <= cy <= c[3] + 1:
                            hit = (ri, ci)
                            break
                    if hit:
                        break
                if hit is None:
                    ok = False
                    break
                grid.setdefault(hit, []).append(r)
            if not ok:
                continue
            ids = {id(r) for r in inside}
            out = [r for r in out if id(r) not in ids]
            # a grid row with a merged (None) cell continues the row above it (a header printed over two lines with
            # cells spanning both): its cells' lines join the same columns of that row
            logical: list[dict] = []
            for ri, row in enumerate(t.rows):
                cols = {ci: grid.get((ri, ci), []) for ci in range(len(row.cells))}
                if logical and any(c is None for c in row.cells):
                    for ci, ls in cols.items():
                        logical[-1].setdefault(ci, []).extend(ls)
                else:
                    logical.append(cols)
            for cols in logical:
                texts = []
                for ci in sorted(cols):
                    ls = sorted(cols[ci], key=lambda r: (round(r[2]), r[1]))
                    if ls:
                        texts.append(' '.join(r[6] for r in ls))
                if texts:
                    y0 = min(r[2] for ls in cols.values() for r in ls)
                    y1 = max(r[4] for ls in cols.values() for r in ls)
                    out.append((pno, X0, y0, X1, y1, body, norm(' '.join(texts)), 0, 'table'))
    return out


def parse(pdf: Path, tables: bool = False) -> dict:
    doc = pymupdf.open(str(pdf))
    raw = []      # (page, x0, y0, x1, y1, size, text-with-markers-dropped, markers)
    sizes: Counter = Counter()
    for pno, page in enumerate(doc):
        for b in page.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                if abs(l['dir'][0] - 1) > 0.01:
                    continue  # rotated text
                for s in l['spans']:
                    if s['text'].strip():
                        sizes[round(s['size'], 1)] += len(s['text'].strip())
    if not sizes:
        return {'units': {}, 'notes': [], 'aside': [], 'sections': 0, 'pages': len(doc), 'text_layer': 0,
                'scan_pages': len(doc), 'invisible': 0}
    body = sizes.most_common(1)[0][0]
    text_layer = sum(sizes.values())
    for pno, page in enumerate(doc):
        for b in page.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                if abs(l['dir'][0] - 1) > 0.01:
                    continue
                parts, marks, big = [], 0, 0.0
                for s in l['spans']:
                    t = s['text']
                    if not t.strip():
                        parts.append(t)
                        continue
                    if s['size'] < 0.8 * body and re.fullmatch(r'\s*[\d*†‡]{1,3}\s*', t):
                        marks += 1
                        continue
                    parts.append(t)
                    big = max(big, s['size'])
                t = norm(''.join(parts))
                if t:
                    x0, y0, x1, y1 = l['bbox']
                    raw.append((pno, x0, y0, x1, y1, big, t, marks))
    if tables:
        raw = table_rows(doc, raw, body)
    # the section column: of the columns where "N." rows start, the ones numbering most distinct sections; of those
    # the right-most (the table of contents numbers the same sections further left; lists inside a section number
    # fewer items further right)
    cols: dict[int, set] = {}
    for r in raw:
        m = SECNO.match(r[6])
        if abs(r[5] - body) < 0.6 and m and len(r[6]) < 6:
            cols.setdefault(round(r[1] / 4) * 4, set()).add(int(m.group(1)))
    best = max((len(v) for v in cols.values()), default=0)
    sec_col = max((x for x, v in cols.items() if len(v) >= max(2, 0.8 * best)), default=None)
    notes, aside, rows, margin = [], [], [], []
    # running heads: lines in the top tenth of the page whose text recurs on a third of the pages (two or more);
    # also (2026-10-31) a line in the top 13% printed with its page number, "4 | P a g e THE ... ACT, 2024", whose
    # rest recurs (the KP Code's heads). A title printed at the top of the first page without a page number stays.
    hc: Counter = Counter()
    for pno in range(len(doc)):
        H = doc[pno].rect.height
        hc.update({(headkey(r[6]) if PAGEPFX.match(r[6]) else ld(r[6])) for r in raw if r[0] == pno and (r[4] < 0.1 * H or (r[4] < 0.13 * H and PAGEPFX.match(r[6]))) and len(headkey(r[6])) >= 4})
    heads = {k for k, v in hc.items() if v >= max(2, -(-len(doc) // 3))} if len(doc) >= 2 else set()
    # the right edge of the text column, over the whole document (a page of tables would pull a per-page edge in)
    ends = Counter(round(r[3] / 3) * 3 for r in raw if r[1] < 0.5 * doc[r[0]].rect.width and abs(r[5] - body) < 0.6)
    doc_edge = ends.most_common(1)[0][0] if ends else None
    by_page: dict[int, list] = {}
    for r in raw:
        by_page.setdefault(r[0], []).append(r)
    for pno in sorted(by_page):
        H = doc[pno].rect.height
        W = doc[pno].rect.width
        ls = sorted(by_page[pno], key=lambda r: (r[2], r[1]))
        # footnotes: small-type rows below the last body-size row of the page
        last_body = max((r[4] for r in ls if r[5] >= 0.9 * body), default=0)
        # the right edge of the text column: where most body rows that start in the left half end (justified text);
        # short lines starting right of it are marginal notes printed on the right (older Acts)
        right_edge = doc_edge if doc_edge else W
        keep = []
        for r in ls:
            if r[5] < 0.85 * body and r[2] >= last_body - 1:
                notes.append({'page': pno + 1, 'text': r[6]})
            elif (PAGENO.match(r[6]) and (r[2] > 0.88 * H or r[4] < 0.13 * H)) or (r[4] < 0.1 * H and ld(r[6]) in heads) or (r[4] < 0.13 * H and PAGEPFX.match(r[6]) and headkey(r[6]) in heads):
                aside.append(r[6])
            elif r[1] > right_edge + 2 and r[1] > 0.6 * W and r[3] - r[1] < 0.25 * W and \
                    not (DESIG.match(r[6]) or PARTIAL.match(r[6])):  # a table's designation column is text
                aside.append(r[6])   # marginal note on the right; joined into blocks like the left ones
                if margin and margin[-1][0] == pno and r[2] - margin[-1][1] < 2.2 * (r[4] - r[2]):
                    margin[-1][2].append(r[6])
                    margin[-1][1] = r[2]
                else:
                    margin.append([pno, r[2], [r[6]]])
            elif sec_col is not None and r[3] < sec_col - 4 and r[1] < 0.4 * W:
                aside.append(r[6])   # marginal note; its lines are also joined into one block below
                if margin and margin[-1][0] == pno and r[2] - margin[-1][1] < 2.2 * (r[4] - r[2]):
                    margin[-1][2].append(r[6])
                    margin[-1][1] = r[2]
                else:
                    margin.append([pno, r[2], [r[6]]])
            else:
                keep.append(r)
        # rows: lines on one baseline
        cur = None
        for r in sorted(keep, key=lambda r: (r[2], r[1])):
            if cur and abs(r[2] - cur['y0']) < 3 and r[0] == cur['page']:
                cur['parts'].append(r)
            else:
                cur = {'page': pno, 'y0': r[2], 'parts': [r]}
                rows.append(cur)
    # a membership table's designation column ("Chairperson", "Member", "Vice" / "Chairperson"): a short designation
    # printed right of the text, well apart from the words beside it, is a cell of its own. The printed order (and
    # pdftotext's) is the whole left cell, then the designation, so it is held back to the end of its paragraph
    # (2026-10-31; before, only a designation that the move_cells() rule below could anchor was moved).
    # the column: where two or more designation lines start at one x on a page
    dcol: Counter = Counter()
    for r in raw:
        if r[1] > 0.55 * doc[r[0]].rect.width and (DESIG.match(r[6]) or PARTIAL.match(r[6])):
            dcol[(r[0], round(r[1] / 3))] += 1
    open_cell = False
    for row in rows:
        ps = sorted(row['parts'], key=lambda r: r[1])
        W0 = doc[row['page']].rect.width
        cells: list[str] = []
        while ps:
            q = ps[-1]
            isdes = (q[1] > 0.55 * W0 and len(q[6].split()) <= 4 and q[6][:1].isupper()
                     and (DESIG.match(q[6]) or PARTIAL.match(q[6])))
            incol = isdes and any(dcol[(q[0], round(q[1] / 3) + d)] >= 2 for d in (-1, 0, 1))
            if isdes and len(ps) > 1 and (q[1] - ps[-2][3] > 12 or (incol and q[1] - ps[-2][3] > 1)):
                cells.insert(0, q[6]); ps = ps[:-1]
            elif isdes and len(ps) == 1 and (open_cell or DESIG.match(q[6])) and not cells:
                cells.insert(0, q[6]); ps = []
            else:
                break
        open_cell = bool(cells) and bool(PARTIAL.match(cells[-1]))
        row['cells'] = cells
        if not ps:
            row['x0'] = row['x1'] = 0
            row['text'] = ''
            row['W'] = W0
            row['table'] = False
            continue
        row['x0'] = ps[0][1]
        row['x1'] = max(p[3] for p in ps)
        row['text'] = norm(' '.join(p[6] for p in ps))
        row['W'] = W0
        row['table'] = any(len(p) > 8 for p in ps)
    aside += [' '.join(m[2]) for m in margin if len(m[2]) > 1]
    # a block can hold two notes printed close together ("... the ordinance." / "Appointment of Inspectors."): each
    # note of the block, split after a line that ends a sentence, is also given (the same set-aside lines)
    for m in margin:
        grp: list[str] = []
        for line in m[2]:
            grp.append(line)
            if re.search(r'[.:]\]?\s*$', line):
                if 1 < len(grp) < len(m[2]):
                    aside.append(' '.join(grp))
                grp = []
        if 1 < len(grp) < len(m[2]):
            aside.append(' '.join(grp))
    # merge footnote rows: a note starts with its number
    merged = []
    for n in notes:
        if re.match(r'^[\d*†‡]{1,3}\s', n['text']) or not merged:
            merged.append(dict(n))
        else:
            merged[-1]['text'] += ' ' + n['text']
    texts = [r['text'] for r in rows]
    # leave out the table of contents
    start = 0
    ci = next((i for i, t in enumerate(texts) if CONTENTS.match(t) or INCONTENTS.search(t)), None)
    if ci is not None and (ci > 0 or INCONTENTS.search(texts[0])):
        key = ld(texts[0]) if ci > 0 else ''
        again = next((j for j in range(ci + 1, len(texts)) if key and ld(texts[j]) == key), None)
        if again is None:
            # the title printed again differently: the first row after the contents that reads as a title, an
            # Act or Ordinance number, the date line or the long title
            again = next((j for j in range(ci + 1, len(texts)) if BODYSTART.match(texts[j])), None)
        if again is not None:
            start = again
    elif ci == 0:
        start = 1
    rows = rows[start:]
    # paragraphs and units
    units: dict[str, dict] = {}
    order: list[tuple[str, list[str], str]] = []
    cur_key, cur_lines, label = '000-title', [], 'Title'
    expect = 1
    nsched = 0
    # the text column: from the section column (or the most common start) to the most common end of a row
    Lb = sec_col if sec_col is not None else (Counter(round(r['x0']) for r in rows).most_common(1)[0][0] if rows else 0)
    Rb = Counter(round(r['x1'] / 3) * 3 for r in rows).most_common(1)[0][0] if rows else 0
    seen: Counter = Counter()

    pending: list[str] = []

    def attach():
        if pending and cur_lines:
            cur_lines[-1] += ' ' + ' '.join(pending).replace('- ', '-')
        pending.clear()

    def flush():
        attach()
        if cur_lines:
            order.append((cur_key, list(cur_lines), label))

    for row in rows:
        t = row['text']
        if not t:
            pending.extend(row['cells'])
            continue
        if row['table']:
            attach()   # a table row: its own line, never a section or Schedule heading
            cur_lines.append(t)
            continue
        m = SECNO.match(t)
        if not m:
            m = SECNO_BARE.match(t)
            if m and int(m.group(1)) != expect:
                m = None
        centred = row['x0'] > Lb + 30 and abs((row['x0'] - Lb) - (Rb - row['x1'])) < 18 and len(t) < 90
        if m and int(m.group(1)) in (expect, expect - 1) and not cur_key.startswith('schedule') and \
                (sec_col is None or abs(row['x0'] - sec_col) < 14 or row['x0'] < sec_col):
            n = int(m.group(1))
            if n == expect - 1 and not m.group(2):
                pass  # "2." again: a list item, not a section
            else:
                flush()
                k = f'sec-{n:03d}' + (f'-{m.group(2).lower()}' if m.group(2) else '')
                seen[k] += 1
                if seen[k] > 1:
                    k += f'-{seen[k]}'
                cur_key, cur_lines, label = k, [t], f'Section {n}{m.group(2)}'
                if not m.group(2):
                    expect = n + 1
                pending.extend(row['cells'])
                continue
        if SCHED.match(t) and centred and cur_key != '000-title':
            flush()
            nsched += 1
            cur_key, cur_lines, label = f'schedule-{nsched:02d}', [t], f'Schedule {nsched}'
            pending.extend(row['cells'])
            continue
        starts = LABEL.match(t) or SECNO.match(t) or NEWPARA.match(t)
        if pending and centred and not starts:
            centred = False   # an indented line of a table's left cell, not a heading: its cell is still open
        if not cur_lines or starts or centred:
            attach()
            cur_lines.append(t)
        else:
            cur_lines[-1] += ' ' + t
        pending.extend(row['cells'])
    flush()
    cells = right_cells(pdf)
    for k, lines, lab in order:
        if cells:
            lines = [move_cells(l, cells) for l in lines]
        units[k] = {'label': lab, 'kind': 'title' if k == '000-title' else ('schedule' if k.startswith('schedule') else 'section'),
                    'text': f'# {lab}\n' + '\n'.join(lines) + '\n'}
    nsec = sum(1 for k in units if k.startswith('sec-'))
    first = texts[0] if texts else ''
    pdf_title = first if re.search(r'(ACT|ORDINANCE|REGULATIONS?|CODE)', first, re.I) and len(first) < 200 else None
    return {'units': units, 'notes': [{'page': n['page'], 'n': (re.match(r'^([\d*†‡]{1,3})', n['text']) or [''])[0],
                                       'g': i + 1, 'text': n['text']} for i, n in enumerate(merged)],
            'note_unit': {}, 'pdf_title': pdf_title, 'aside': sorted(set(aside)), 'sections': nsec, 'pages': len(doc),
            'text_layer': text_layer, 'scan_pages': 0, 'invisible': 0, 'heads': []}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    out = parse(Path(sys.argv[1]))
    print('sections', out['sections'], 'aside', out['aside'][:10])
    for k, u in out['units'].items():
        print('=====', k)
        print(u['text'])
    for n in out['notes']:
        print('NOTE', n)
