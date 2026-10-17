"""Exercise the real, silent first-run path in a new disposable output directory.

Run from the repository: python scripts/smoke_check.py --output-dir outputs/smoke-check
No models, network services or credentials are needed. The public example is
copied before its fourth scene is edited; its source files are never changed.
"""
import argparse
import hashlib
import html
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

from p2v.pipeline import _ffmpeg, _hash, _json, _require, _timestamp, _write_json


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/antigen_escape'
SCENE_IDS = [f's{number:02d}' for number in range(1, 8)]


def _environment():
    version = subprocess.run([_ffmpeg(), '-version'], check=True, capture_output=True,
                             encoding='utf-8', errors='replace', timeout=30)
    return {
        'system': platform.system(), 'machine': platform.machine(),
        'python': platform.python_version(),
        'Pillow': importlib.metadata.version('Pillow'),
        'imageio_ffmpeg': importlib.metadata.version('imageio-ffmpeg'),
        'ffmpeg': version.stdout.splitlines()[0],
    }


def _cli(arguments):
    environment = os.environ.copy()
    environment.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/pipeline.py'), *arguments],
                            cwd=ROOT, env=environment, capture_output=True, encoding='utf-8',
                            errors='replace', timeout=900)
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError('CLI ' + arguments[0] + ' did not return valid JSON') from exc
    _require(result.returncode == 0 and payload.get('ok') is True,
             'CLI ' + arguments[0] + ' failed: ' + str(payload.get('errors', payload.get('error', 'unknown error'))))
    return payload


def _new_output(value):
    lexical = Path(value).expanduser().absolute()
    _require(not any(path.is_symlink() for path in (lexical, *lexical.parents)),
             'smoke output or its parents may not be symlinks')
    output = lexical.resolve()
    _require(output not in (Path(output.anchor), Path.home().resolve()), 'unsafe smoke output directory')
    _require(not output.is_relative_to(EXAMPLE.resolve()), 'smoke output must be outside the original example')
    if output.exists():
        _require(output.is_dir() and not any(output.iterdir()),
                 'smoke output already exists and is not an empty directory; choose a new directory')
    _require(not any(path.is_symlink() for path in EXAMPLE.rglob('*')), 'public example may not contain symlinks')
    output.mkdir(parents=True, exist_ok=True)
    return output


def _subtitles_and_evidence(project, report, build_dir):
    scenes, timeline = project['scenes'], report['scenes']
    _require([scene['id'] for scene in scenes] == SCENE_IDS, 'expected seven public example scenes')
    _require([cue['id'] for cue in timeline] == SCENE_IDS, 'build timeline scenes differ from the project')
    srt, vtt = [], ['WEBVTT', '']
    elapsed_frames = 0
    for number, (scene, cue) in enumerate(zip(scenes, timeline), 1):
        start = elapsed_frames / report['fps']
        end = start + cue['audio_duration_seconds']
        _require(math.isclose(cue['start_seconds'], start, abs_tol=1e-8), 'scene start is not continuous')
        elapsed_frames += cue['frames']
        _require(math.isclose(cue['end_seconds'], elapsed_frames / report['fps'], abs_tol=1e-8),
                 'scene end differs from frame count')
        _require(start < end <= cue['end_seconds'] + 1e-8, 'subtitle would overlap the following scene')
        text = scene['display_text'].replace('\r', '').strip()
        srt.extend([str(number), f'{_timestamp(start)} --> {_timestamp(end)}', text, ''])
        vtt.extend([f'{_timestamp(start, ".")} --> {_timestamp(end, ".")}', html.escape(text), ''])
    _require(report['frames'] == elapsed_frames and
             math.isclose(report['duration_seconds'], elapsed_frames / report['fps'], abs_tol=1e-8),
             'total duration or frame count differs from scene timeline')
    for name, lines in (('subtitles.srt', srt), ('subtitles.vtt', vtt)):
        _require((build_dir / name).read_text(encoding='utf-8') == '\n'.join(lines) + '\n',
                 name + ' does not match all seven authored cues and timeline')
    evidence = (build_dir / 'evidence.html').read_text(encoding='utf-8')
    units = {unit['id']: unit for unit in project['source']['units']}
    source_path = build_dir.parent / 'project' / project['source']['path']
    _require(_hash(source_path) == project['source']['sha256'], 'working source bytes changed')
    source_lines = source_path.read_text(encoding='utf-8-sig').splitlines()
    quote_count = 0
    for claim in project['claims']:
        _require(html.escape(claim['text']) in evidence, 'evidence page omits a claim')
        for anchor in claim['evidence']:
            unit = units[anchor['unit_id']]
            locator = unit['locator']
            _require(locator['kind'] == 'text' and source_lines[locator['line'] - 1] == unit['text'],
                     'evidence unit or locator differs from the actual source')
            _require(anchor['quote'] in unit['text'], 'claim quote is not present in the source unit')
            _require('<blockquote>' + html.escape(anchor['quote']) + '</blockquote>' in evidence,
                     'evidence page omits an escaped source quote')
            _require(html.escape(unit['id'] + ' · line ' + str(locator['line'])) in evidence,
                     'evidence page omits a source locator')
            quote_count += 1
    return {'subtitle_cues': len(scenes), 'evidence_claims': len(project['claims']),
            'source_evidence_quotes': quote_count}


def _decode(build_dir, report):
    executable, video = _ffmpeg(), build_dir / 'video.mp4'
    full = subprocess.run([executable, '-nostdin', '-hide_banner', '-loglevel', 'error',
                           '-i', str(video), '-map', '0:v:0', '-map', '0:a:0',
                           '-progress', 'pipe:1', '-f', 'null', '-'],
                          capture_output=True, timeout=900)
    _require(full.returncode == 0, 'complete video/audio decode failed')
    frames = re.findall(rb'^frame=(\d+)\s*$', full.stdout, re.MULTILINE)
    _require(frames and int(frames[-1]) == report['frames'], 'decoded frames differ from the timeline')
    # Decode PCM into a temporary stream; never retain an entire audio track in RAM.
    with tempfile.TemporaryFile() as pcm:
        audio = subprocess.run([executable, '-nostdin', '-hide_banner', '-loglevel', 'info',
                                '-i', str(video), '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '48000',
                                '-c:a', 'pcm_s16le', '-f', 's16le', 'pipe:1'],
                               stdout=pcm, stderr=subprocess.PIPE, timeout=900)
        _require(audio.returncode == 0 and re.search(rb'Audio:\s*aac\b', audio.stderr),
                 'AAC track missing or could not be completely decoded')
        size = pcm.tell()
        samples = size // 2
        _require(size > 0 and size % 2 == 0 and
                 abs(samples - round(report['duration_seconds'] * 48000)) <= 2048,
                 'decoded audio length differs from the video duration')
        pcm.seek(0)
        for chunk in iter(lambda: pcm.read(65536), b''):
            _require(not any(chunk), 'public preview audio contains nonzero samples')
    return {'decoded_frames': int(frames[-1]), 'decoded_aac_samples': samples,
            'all_audio_samples_zero': True}


def _cache_snapshot(build_dir, report):
    snapshots = {}
    for scene in report['scenes']:
        key = hashlib.sha256(scene['id'].encode('utf-8')).hexdigest()[:24]
        snapshots[scene['id']] = {}
        for kind, filename, digest_key in (('audio', 'narration.wav', 'audio_sha256'),
                                            ('clip', 'clip.mp4', 'clip_sha256')):
            path = build_dir / '.p2v-cache' / key / filename
            _require(path.is_file() and not path.is_symlink(), 'missing or invalid scene cache payload')
            digest = _hash(path)
            _require(digest == scene[digest_key], 'scene cache hash differs from its build report')
            snapshots[scene['id']][kind] = {'sha256': digest, 'bytes': path.stat().st_size,
                                           'mtime_ns': path.stat().st_mtime_ns}
    return snapshots


def _check_build(project, report, build_dir):
    _require(report.get('automated_passed') is True and report.get('scientific_guarantee') is False,
             'build did not pass or incorrectly claimed a scientific guarantee')
    _require(report.get('audio_mode') == 'silence' and report.get('narration_present') is False,
             'smoke check must use the explicit silent example')
    _require(report.get('human_review') == project['acceptance'], 'build changed human review states')
    names = {'video.mp4', 'subtitles.srt', 'subtitles.vtt', 'evidence.html'}
    _require(set(report['outputs']) == names, 'declared output file set is incomplete or unexpected')
    for name in names:
        path, record = build_dir / name, report['outputs'][name]
        _require(path.is_file() and not path.is_symlink() and path.stat().st_size == record['bytes']
                 and _hash(path) == record['sha256'], 'declared output hash or size differs: ' + name)
    return {**_subtitles_and_evidence(project, report, build_dir), **_decode(build_dir, report),
            'declared_output_hashes_verified': len(names)}


def _safe_error(error, output):
    value = str(error)
    # CLI diagnostics may mention paths. Persistent reports never retain them.
    for path in sorted((output, ROOT, Path.home()), key=lambda item: len(str(item)), reverse=True):
        for spelling in (str(path), str(path).replace('\\', '/'), str(path).replace('/', '\\')):
            value = value.replace(spelling, '<local>')
    return type(error).__name__ + ': ' + value


def run(output, width, fps):
    summary = {'schema_version': 1, 'ok': False, 'environment': _environment(),
               'width': width, 'fps': fps, 'stages': {},
               'note': 'Technical silent-example check only; human science and visual review remain separate.'}
    project_dir, build_dir = output / 'project', output / 'build'
    original_hashes = {path.relative_to(EXAMPLE).as_posix(): _hash(path)
                       for path in EXAMPLE.rglob('*') if path.is_file()}
    shutil.copytree(EXAMPLE, project_dir)
    project_path = project_dir / 'project.json'
    shutil.copy2(project_path, project_dir / 'project.original.json')
    try:
        validation = _cli(['validate', str(project_path)])
        _require(validation.get('build_ready') is True, 'CLI validation did not mark the example build-ready')
        summary['validate'] = {'ok': True, 'contract_valid': validation.get('contract_valid'),
                               'build_ready': validation['build_ready']}
        arguments = ['build', str(project_path), '--output-dir', str(build_dir),
                     '--width', str(width), '--fps', str(fps)]
        baseline_report, baseline_cache = None, None
        for stage in ('baseline', 'unchanged', 'revision'):
            if stage == 'revision':
                project = _json(project_path)
                scene = next(item for item in project['scenes'] if item['id'] == 's04')
                scene['visual']['title'] = 'Target loss breaks single-target recognition'
                _write_json(project_path, project)
            _cli(arguments + ([] if stage == 'baseline' else ['--resume']))
            project, report = _json(project_path), _json(build_dir / 'build_report.json')
            checks = _check_build(project, report, build_dir)
            snapshots = _cache_snapshot(build_dir, report)
            expected = {'audio_reused': 0 if stage == 'baseline' else 7,
                        'clips_reused': 0 if stage == 'baseline' else (7 if stage == 'unchanged' else 6),
                        'audio_built': 7 if stage == 'baseline' else 0,
                        'clips_built': 7 if stage == 'baseline' else (0 if stage == 'unchanged' else 1)}
            _require(report['cache'] == expected, stage + ' cache reuse counts differ from expectations')
            if stage == 'baseline':
                baseline_report, baseline_cache = report, snapshots
            else:
                changed = []
                for scene_id in SCENE_IDS:
                    for kind in ('audio', 'clip'):
                        before, after = baseline_cache[scene_id][kind], snapshots[scene_id][kind]
                        if before != after:
                            changed.append(scene_id + '.' + kind)
                _require(changed == ([] if stage == 'unchanged' else ['s04.clip']),
                         stage + ' changed unexpected cache hashes, sizes or modification times')
                if stage == 'revision':
                    _require(baseline_cache['s04']['clip']['sha256'] != snapshots['s04']['clip']['sha256'] and
                             baseline_cache['s04']['clip']['mtime_ns'] != snapshots['s04']['clip']['mtime_ns'],
                             'the revised s04 clip was not actually rebuilt with different content')
                for before, after in zip(baseline_report['scenes'], report['scenes']):
                    for key in ('start_seconds', 'end_seconds', 'frames', 'audio_duration_seconds', 'pause_duration_seconds'):
                        _require(before[key] == after[key], stage + ' changed authored scene timing')
                for name in ('subtitles.srt', 'subtitles.vtt', 'evidence.html'):
                    _require(baseline_report['outputs'][name] == report['outputs'][name],
                             stage + ' changed an unrelated output: ' + name)
                if stage == 'unchanged':
                    _require(baseline_report['outputs']['video.mp4'] == report['outputs']['video.mp4'],
                             'unchanged resume changed the final video payload')
                checks['changed_cache_payloads'] = changed
            _write_json(output / (stage + '_build_report.json'), report)
            summary['stages'][stage] = {'ok': True, 'duration_seconds': report['duration_seconds'],
                                         'frames': report['frames'], 'cache': report['cache'],
                                         'checks': checks, 'outputs': report['outputs'],
                                         'cache_payloads': snapshots}
            print(json.dumps({'stage': stage, 'ok': True, 'cache': report['cache'], 'checks': checks}), flush=True)
        _require(original_hashes == {path.relative_to(EXAMPLE).as_posix(): _hash(path)
                                    for path in EXAMPLE.rglob('*') if path.is_file()},
                 'original public example files changed during the smoke check')
        summary['original_example_unchanged'] = True
        summary['changed_only_s04'] = True
        summary['ok'] = True
    except (OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError) as exc:
        summary['error'] = _safe_error(exc, output)
    _write_json(output / 'smoke_report.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('outputs/smoke-check'))
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--fps', type=int, default=12)
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser().absolute()
    try:
        _require(320 <= args.width <= 4096 and args.width % 32 == 0, 'width must be a multiple of 32 within 320-4096')
        _require(12 <= args.fps <= 60, 'fps must be within 12-60')
        output = _new_output(args.output_dir)
        result = run(output, args.width, args.fps)
        print(json.dumps({'ok': result['ok'], 'report': 'smoke_report.json',
                          'changed_only_s04': result.get('changed_only_s04', False),
                          **({'error': result['error']} if 'error' in result else {})}))
        return 0 if result['ok'] else 1
    except (OSError, ValueError, ImportError, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'error': _safe_error(exc, output)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
