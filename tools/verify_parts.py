"""Verify new corpus.d parts of a Pakistan provincial repo before PUBLISH (private).

    python -X utf8 verify_parts.py <scripts/<slug>-law> <part.json> [...]

1. check_letters.py of that folder on each part (0 mismatches required);
2. a scratch build of every part that has PUBLISH plus these parts into a temporary repository, and check.py on it
   (0 mismatches, 0 trailer errors, ...);
3. audit_push over the scratch main (what pushing it would add);
4. every act already on the remote main keeps its tree: for each law path on the last remote main, the blob in the
   scratch main is the same (the published text is unchanged).
Prints one JSON line; exit 0 only when all four hold.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / 'gitlaw_common'
sys.path.insert(0, str(COMMON))
import private  # noqa: E402


def git(repo, *a):
    return subprocess.run(['git', *a], cwd=repo, capture_output=True, text=True, encoding='utf-8').stdout.strip()


def main():
    folder = Path(sys.argv[1]).resolve()
    parts = [Path(p).resolve() for p in sys.argv[2:]]
    slug = folder.name
    out = {'parts': [p.name for p in parts]}
    cl = subprocess.run([sys.executable, '-X', 'utf8', 'check_letters.py', *map(str, parts)], cwd=folder,
                        capture_output=True, text=True, encoding='utf-8')
    out['letters'] = cl.stdout.strip().splitlines()[-1] if cl.stdout.strip() else cl.stderr[-300:]
    out['letters_ok'] = cl.returncode == 0
    # scratch build: only published parts + these, by hiding other unverified parts behind a temporary copy
    with tempfile.TemporaryDirectory(prefix=f'{slug}-verify-') as td:
        td = Path(td)
        fake = td / slug
        (fake / 'corpus.d').mkdir(parents=True)
        for p in sorted((folder / 'corpus.d').glob('*.json')):
            if p.with_suffix('.PUBLISH').exists() or p.resolve() in parts:
                (fake / 'corpus.d' / p.name).write_bytes(p.read_bytes())
        for name in ('PUBLISH', 'corpus.json', 'verification.json'):
            if (folder / name).exists():
                (fake / name).write_bytes((folder / name).read_bytes())
        if (folder / 'repo').exists():
            subprocess.run(['cp', '-r', str(folder / 'repo'), str(fake / 'repo')], check=True)
        repo = td / 'build'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
        env = {**os.environ, 'GITLAW_VERIFIED_PARTS_ONLY': '0'}
        b = subprocess.run([sys.executable, '-X', 'utf8', str(COMMON / 'build.py'), str(fake), '--repo', str(repo),
                            '--docs-date', '2026-10-30'], capture_output=True, text=True, encoding='utf-8', env=env)
        if b.returncode:
            out['build'] = (b.stderr or b.stdout)[-800:]
            print(json.dumps(out)); return 1
        c = subprocess.run([sys.executable, '-X', 'utf8', str(COMMON / 'check.py'), str(repo), '--corpus',
                            str(fake / 'corpus.json')], capture_output=True, text=True, encoding='utf-8')
        try:
            chk = json.loads(c.stdout)
            chk.pop('details', None)
        except ValueError:
            chk = {'error': (c.stderr or c.stdout)[-500:]}
        out['check'] = chk
        out['check_ok'] = c.returncode == 0
        out['audit'] = private.audit_push(repo, 'main')
        # published trees unchanged: compare with the remote main as fetched into the local clone
        clone = ROOT.parent.parent / slug
        remote = git(clone, 'ls-remote', 'origin', 'refs/heads/main').split()[0]
        out['remote_main'] = remote[:9]
        old = dict(l.split('\t', 1)[::-1] for l in git(clone, 'ls-tree', '-r', remote).splitlines() if '\t' in l)
        new = dict(l.split('\t', 1)[::-1] for l in git(repo, 'ls-tree', '-r', 'main').splitlines() if '\t' in l)
        law = [k for k in old if k.count('/') >= 1 and not k.startswith(('tools/', 'data/', '.github/'))
               and k not in ('README.md',)]
        changed = [k for k in law if k.endswith('.md') and k.split('/')[0] not in ('docs',) and new.get(k) != old.get(k)]
        out['published_paths'] = len(law)
        out['published_changed'] = changed[:20]
        out['commits'] = git(repo, 'rev-list', '--count', 'main')
    ok = (out['letters_ok'] and out['check_ok'] and not out['audit'] and not out['published_changed']
          and out['published_paths'] > 0)
    out['ok'] = ok
    print(json.dumps(out, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
