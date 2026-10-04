"""Check the actual release files and relative Markdown links, without network."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def verify(root):
    errors = []
    work_dirs = {'__pycache__', '.git', '.venv', 'venv', 'outputs'}
    files = sorted(p for p in root.rglob('*') if p.is_file() and not any(part in work_dirs for part in p.relative_to(root).parts))
    for path in files:
        relative = path.relative_to(root).as_posix()
        if any(part in ('__pycache__', '.git', '.runtime', '.venv', 'outputs') for part in path.relative_to(root).parts) or path.suffix.lower() in ('.pyc', '.wav', '.mp3') or path.name.startswith('.env'):
            errors.append('unexpected private/cache/output file: ' + relative)
        if path.suffix.lower() not in ('.md', '.py', '.txt', '.json', '.html', '.srt', '.vtt', '.yml', '.yaml'):
            continue
        text = path.read_text(encoding='utf-8-sig')
        if re.search(r'(?i)[a-z]:[\\/](?:Users|Documents)[\\/]|file:/{3}', text):
            errors.append('local absolute path: ' + relative)
        # Flag concrete provider credentials; names/placeholders in guidance are allowed.
        if re.search(r'(?:sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,}|(?i:Bearer)\s+[A-Za-z0-9_-]{24,})', text):
            errors.append('possible credential: ' + relative)
        if path.suffix.lower() == '.md':
            for target in re.findall(r'\]\(([^)]+)\)', text):
                target = target.split('#', 1)[0]
                if not target or '://' in target or target.startswith('mailto:'):
                    continue
                if not (path.parent / target).resolve().exists():
                    errors.append('missing relative link: ' + relative + ' -> ' + target)
    return {'passed': not errors, 'errors': errors, 'file_count': len(files), 'files': [{'path': p.relative_to(root).as_posix(), 'size': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = verify(args.root.resolve())
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
