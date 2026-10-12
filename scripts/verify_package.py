"""Check the actual release files and relative Markdown links, without network."""
import argparse
import hashlib
import json
from pathlib import Path
import re


AUDIO_EXTENSIONS = {
    '.wav', '.wave', '.mp3', '.mp2', '.flac', '.ogg', '.oga', '.opus',
    '.m4a', '.m4b', '.m4p', '.aac', '.adts', '.wma', '.aif', '.aiff',
    '.aifc', '.amr', '.au', '.snd', '.caf', '.ac3', '.dts', '.mka',
    '.weba', '.pcm', '.ape', '.alac',
}


def verify(root):
    errors = []
    work_dirs = {'__pycache__', '.git', '.venv', 'venv', 'outputs'}
    files = sorted(p for p in root.rglob('*') if p.is_file() and not any(part in work_dirs for part in p.relative_to(root).parts))
    for path in files:
        relative = path.relative_to(root).as_posix()
        unexpected_audio = path.suffix.lower() in AUDIO_EXTENSIONS
        if any(part in ('__pycache__', '.git', '.runtime', '.venv', 'outputs') for part in path.relative_to(root).parts) or path.suffix.lower() == '.pyc' or unexpected_audio or path.name.startswith('.env'):
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
    manifest_path = root / 'RELEASE_MANIFEST.json'
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
            declared = {entry['path']: entry for entry in manifest['files']}
            actual = {p.relative_to(root).as_posix(): p for p in files if p.name != 'RELEASE_MANIFEST.json'}
            if set(declared) != set(actual) or len(declared) != len(manifest['files']):
                errors.append('release manifest file set differs from actual package')
            for relative, path in actual.items():
                entry = declared.get(relative)
                if entry and (entry['size'] != path.stat().st_size or entry['sha256'] != hashlib.sha256(path.read_bytes()).hexdigest()):
                    errors.append('release manifest hash/size mismatch: ' + relative)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append('invalid release manifest: ' + str(exc))
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
