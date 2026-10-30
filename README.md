# Balochistan: law history in git

The Acts, Ordinances and Regulations of the Province of Balochistan (Pakistan) as a git history: one file per section, one paragraph per line, so `git blame`, `git log` and `git diff` work line by line. The text is the English text published on the Balochistan Code.

It follows the shared design of [lexifina/global-law](https://github.com/lexifina/global-law).

## What this repository holds

**Current text only, not yet a history.** The Balochistan Code publishes one PDF per law, with no earlier versions. So each law is one commit holding its whole text as published, dated by the day it was retrieved and credited to the department ("oldest version available"), not to an amending Act.

| Folder | What |
| --- | --- |
| one folder per law (by its title, e.g. `the-balochistan-archives-act-2014/`) | the law: `000-title.md` (number, date, long title and preamble), one file per section, one per Schedule |
| `data/amendments.csv` | every footnote: the publication and assent notes, and which law inserted, substituted or omitted which words |

The laws are added in parts of about fifty, in the order of the Code's alphabetical list. A law is left out until it can be read reliably: laws titled as repealed, scans without a text layer, PDFs whose layout the parser does not yet handle, and any PDF whose text fails the independent check below. Where the Code lists two files for one law, only the first that passes is used. Rules, gazette notifications and policies are not included.

## Source

[Balochistan Code](https://balochistancode.gob.pk/laws_rules.aspx?wise=alphabetical&opento=1), Law and Parliamentary Affairs Department, Government of Balochistan: one PDF per law. Each PDF's sha256 is recorded with its version in `data/versions.json`.

## Dates

Each law's version is dated by the day it was retrieved from the Balochistan Code, at noon in Quetta (Asia/Karachi). That is not the day of its enactment or of its last amendment; the Code gives no "as amended up to" date.

## How it is built

Lexifina reads the sources listed here and records each act's dated versions, and the laws that made each change, in one corpus file. `tools/build.py` writes this repository from that file, and the same corpus always gives the same commit hashes; `REPRODUCE.md` gives the details and the checks. A model (Claude) wrote Lexifina's code; it wrote no legal text, and no model runs when the history is built.

The text layer of each PDF (no OCR) becomes one file per section. The table of contents, the marginal notes (the section headings printed in the margin), running heads, page numbers and footnote numbers are left out. The footnotes are kept in `data/amendments.csv`. Square brackets marking amended words stay as printed. Chapter and part headings stand above the first section under them. In membership tables the designation column ("Chairman", "Member") is read after the cell beside it, as printed.

## How it is checked

Every version is read back from git on the day it took effect and must match the corpus. A second, independent reading of every PDF (a different PDF engine) must contain every letter and digit of each law in the same order, with nothing in the body left out. Results are in `REPRODUCE.md`.

## What "author" means

The author of each commit is the publisher (the Law and Parliamentary Affairs Department), with an e-mail address that cannot exist; the committer is always Lexifina.

## Limits

Only the text as published is here: no earlier versions. Section headings, printed only as marginal notes, are left out. The authoritative text is the Balochistan Gazette. Federal laws that apply in the province are in [lexifina/pakistan-law](https://github.com/lexifina/pakistan-law).

## Licence

See [LICENSE](LICENSE): the laws are reproduced under the Copyright Ordinance, 1962, s. 57(1)(q)(i). Source: Balochistan Code, Law and Parliamentary Affairs Department, Government of Balochistan.
