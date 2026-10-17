"""Validate sources, build measured audiovisual timelines, and reuse unchanged scenes.

The Agent authors the claims, narration, and supported visual plan. These helpers
check and execute that plan; they do not interpret a PDF or certify its science.
Only standard-library modules are imported before a build/doctor needs extras.
"""
import argparse
import copy
import hashlib
import html
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import wave

from . import __version__

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
CACHE_SCHEMA = 1
OUTPUT_MARKER = '.p2v-output.json'


def _json(path):
    def reject_constant(value):
        raise ValueError('JSON has a non-finite number: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=reject_constant)


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.pending')
    _require(not path.is_symlink() and not temporary.is_symlink(), 'JSON output may not be a symlink')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _resolve(base, value, description):
    _require(_text(value), description + ' needs a local path')
    _require(not re.match(r'^[a-zA-Z]+://', value), description + ' must be a local file')
    path = Path(value).expanduser()
    return (base / path if not path.is_absolute() else path).resolve()


def _contract_module():
    entry = PACKAGE_ROOT / 'skills/paper-to-video/scripts/project.py'
    spec = importlib.util.spec_from_file_location('p2v_source_contract', entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_project(project_path):
    path = Path(project_path).expanduser().resolve()
    project = _json(path)
    _require(isinstance(project, dict), 'project must be a JSON object')
    return project, path


def _source_check(project, base):
    """Compare the pinned bytes AND imported units with their actual source."""
    source = project['source']
    path = _resolve(base, source.get('path'), 'source')
    _require(path.is_file(), 'source file does not exist')
    actual = _hash(path)
    _require(actual == source['sha256'], 'source SHA256 mismatch; re-extract and review the changed source')
    contract = _contract_module()
    imported = contract.create_project(path, source['format'], project['project']['article_type'],
                                       source['coverage'], project['project']['language'], None)
    actual_units = {unit['id']: unit for unit in imported['source']['units']}
    project_units = {unit['id']: unit for unit in source['units']}
    for unit_id, unit in project_units.items():
        _require(unit_id in actual_units, 'source unit not found in actual file: ' + unit_id)
        expected = actual_units[unit_id]
        _require(unit['text'] == expected['text'] and unit['locator'] == expected['locator'],
                 'source text/locator differs from actual file: ' + unit_id)
    if source['coverage'] == 'full':
        _require(set(project_units) == set(actual_units), 'full source coverage omits imported units')
    imported_issues = set(imported['source'].get('upstream_issues', []))
    _require(imported_issues.issubset(set(source.get('upstream_issues', []))),
             'project omits upstream extraction issues from actual source')
    return {'sha256': actual, 'units_checked': len(project_units), 'source_format': source['format']}


def _render_config(project, width=None, fps=None):
    top_level = project.get('render')
    legacy_nested = project['project'].get('render')
    if top_level is not None and legacy_nested is not None:
        _require(top_level == legacy_nested, 'conflicting root render and project.render configurations')
    config = top_level if top_level is not None else legacy_nested
    _require(isinstance(config, dict) and config.get('schema_version') == 1,
             'render requires schema_version 1; add an authored rendering plan')
    config = copy.deepcopy(config)
    config['width'] = config.get('width', 1920) if width is None else width
    config['fps'] = config.get('fps', 24) if fps is None else fps
    _require(type(config['width']) is int and 320 <= config['width'] <= 4096 and config['width'] % 32 == 0,
             'width must be a multiple of 32 between 320 and 4096')
    _require(type(config['fps']) is int and 12 <= config['fps'] <= 60,
             'fps must be an integer between 12 and 60')
    pause = config.get('pause_seconds', 0.35)
    _require(type(pause) in (int, float) and math.isfinite(pause) and 0 <= pause <= 3,
             'pause_seconds must be finite and between 0 and 3')
    config['pause_seconds'] = pause
    _require(isinstance(config.get('audio'), dict), 'render needs audio configuration')
    _require(config['audio'].get('engine') in ('kokoro_onnx', 'import', 'silence'), 'unsupported audio engine')
    return config


def _override_audio(config, audio_config_path):
    if audio_config_path is None:
        return config
    path = Path(audio_config_path).expanduser().resolve()
    override = _json(path)
    _require(isinstance(override, dict), 'audio override must be a JSON audio configuration object')
    combined = copy.deepcopy(config['audio'])
    if override.get('engine', combined.get('engine')) != combined.get('engine'):
        combined = {}
    for key, value in override.items():
        if key in ('path', 'model_path', 'voices_path'):
            value = str(_resolve(path.parent, value, 'audio override ' + key))
        elif key == 'clips':
            _require(isinstance(value, dict), 'audio override clips must be an object')
            value = {scene_id: str(_resolve(path.parent, clip, 'audio override clip')) for scene_id, clip in value.items()}
        combined[key] = value
    _require(combined.get('engine') in ('kokoro_onnx', 'import', 'silence'), 'unsupported audio override engine')
    config['audio'] = combined
    return config


def _asset_check(config, base):
    assets = config.get('assets', {})
    _require(isinstance(assets, dict), 'render.assets must be an object keyed by asset id')
    checked = {}
    for asset_id, asset in assets.items():
        _require(_text(asset_id) and isinstance(asset, dict), 'asset needs id and configuration object')
        path = _resolve(base, asset.get('path'), 'asset ' + asset_id)
        _require(path.is_file(), 'asset file missing: ' + asset_id)
        _require(_text(asset.get('rights')) and _text(asset.get('attribution')),
                 'asset needs explicit rights and attribution: ' + asset_id)
        digest = _hash(path)
        _require(digest == asset.get('sha256'), 'asset SHA256 mismatch: ' + asset_id)
        checked[asset_id] = {'sha256': digest, 'rights': asset['rights'], 'attribution': asset['attribution']}
    if config.get('font') is not None:
        font = _resolve(base, config['font'], 'font')
        _require(font.is_file(), 'configured font file missing')
        checked['_font'] = {'sha256': _hash(font)}
    return checked


def _audio_config(config, scene, base):
    """A selected import file/model is fingerprinted, never the current cwd."""
    audio = copy.deepcopy(config['audio'])
    dependency_hashes = {}
    if audio['engine'] == 'import':
        clips = audio.pop('clips', None)
        selected = scene.get('audio_path')
        if selected is None:
            _require(isinstance(clips, dict) and _text(clips.get(scene['id'])),
                     'import audio needs clips entry for scene: ' + scene['id'])
            selected = clips[scene['id']]
        path = _resolve(base, selected, 'import audio for ' + scene['id'])
        _require(path.is_file(), 'import audio file missing for scene: ' + scene['id'])
        dependency_hashes['import_wav'] = _hash(path)
        _wave_info(path)
        audio['path'] = str(path)
    elif audio['engine'] == 'silence':
        durations = audio.pop('durations', None)
        _require(isinstance(durations, dict) and scene['id'] in durations,
                 'silent preview needs a planned duration for scene: ' + scene['id'])
        audio['duration_seconds'] = durations[scene['id']]
    else:
        for key in ('model_path', 'voices_path'):
            path = _resolve(base, audio.get(key), key)
            _require(path.is_file(), key + ' file missing; doctor explains required dependencies')
            dependency_hashes[key] = _hash(path)
            audio[key] = str(path)
    return audio, dependency_hashes


def validate_project(project_path, width=None, fps=None, visual_validator=None, audio_config_path=None):
    errors = []
    automated = {}
    try:
        project, path = load_project(project_path)
        structural = _contract_module().validate(project)
        errors.extend(structural['errors'])
        if errors:
            return {'ok': False, 'contract_valid': False, 'build_ready': False,
                    'errors': errors, 'pending': structural['pending'], 'automated_checks': automated}
        automated['contract'] = True
        automated['source'] = _source_check(project, path.parent)
        automated['quotes'] = sum(len(claim['evidence']) for claim in project['claims'])
        _require(project['project']['article_type'] != 'unknown', 'classify article_type before rendering')
        _require(project['claims'] and project['scenes'], 'prepare claims and scenes before rendering')
        scope = project['project'].get('scope', 'full_paper')
        _require(project['source']['coverage'] == 'full' or scope == 'focused_excerpt',
                 'limited source coverage blocks full-paper production; explicitly describe a focused_excerpt')
        unresolved = [item for item in structural['pending'] if item.startswith('upstream extraction issue:')]
        _require(not unresolved, '; '.join(unresolved))
        config = _override_audio(_render_config(project, width, fps), audio_config_path)
        automated['assets'] = _asset_check(config, path.parent)
        runtime = copy.deepcopy(project)
        runtime['_base_dir'] = str(path.parent)
        runtime['render'] = config
        runtime['project'].pop('render', None)
        if visual_validator is None:
            visual_validator = importlib.import_module('p2v.renderer').validate_visual
        automated['visual_components'] = [visual_validator(runtime, scene) for scene in project['scenes']]
        for scene in project['scenes']:
            audio_config, _ = _audio_config(config, scene, path.parent)
            # Structural source/visual failures have already been checked. Import
            # PCM validation is internal; synthesis providers validate locally.
            if audio_config['engine'] != 'import':
                importlib.import_module('p2v.audio').validate_config(audio_config)
        automated['audio_inputs'] = True
        return {'ok': True, 'contract_valid': True, 'build_ready': True,
                'evidence_ready': structural['evidence_ready'], 'errors': [],
                'pending': structural['pending'], 'automated_checks': automated,
                'human_review': copy.deepcopy(project['acceptance']),
                'note': 'Ready to build a review draft. Automated checks do not approve scientific meaning, pronunciation, or aesthetics.'}
    except (OSError, KeyError, TypeError, ValueError, ImportError, AttributeError, wave.Error) as exc:
        errors.append(str(exc))
        return {'ok': False, 'contract_valid': bool(automated.get('contract')), 'build_ready': False,
                'errors': errors, 'pending': [], 'automated_checks': automated}


def _wave_info(path):
    with wave.open(str(path), 'rb') as audio:
        _require(audio.getcomptype() == 'NONE' and audio.getsampwidth() == 2 and audio.getnchannels() in (1, 2),
                 'audio must be uncompressed PCM16 WAV with one or two channels')
        frames, rate = audio.getnframes(), audio.getframerate()
        _require(frames > 0 and 8000 <= rate <= 96000, 'audio WAV is empty or outside 8–96 kHz')
        # Reading proves the WAV header does not describe data missing from disk.
        sample_bytes = audio.readframes(frames)
        _require(len(sample_bytes) == frames * audio.getnchannels() * audio.getsampwidth(), 'audio WAV data is truncated')
        return {'duration_seconds': frames / rate, 'sample_rate': rate, 'samples': frames,
                'channels': audio.getnchannels(), 'sample_width': audio.getsampwidth()}


def _within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _prepare_output(project_path, project, output_dir):
    original = Path(output_dir).expanduser().absolute()
    _require(not original.is_symlink(), 'output directory may not be a symlink')
    output = original.resolve()
    _require(output != Path(output.anchor) and output != Path.home().resolve(), 'unsafe output directory')
    protected = [project_path, _resolve(project_path.parent, project['source']['path'], 'source')]
    config = project['render']
    protected += [_resolve(project_path.parent, asset['path'], 'asset') for asset in config.get('assets', {}).values()]
    audio = config['audio']
    protected += [_resolve(project_path.parent, path, 'import audio') for path in audio.get('clips', {}).values()]
    protected += [_resolve(project_path.parent, scene['audio_path'], 'import audio') for scene in project['scenes'] if scene.get('audio_path')]
    protected += [_resolve(project_path.parent, audio[key], key) for key in ('model_path', 'voices_path') if audio.get(key)]
    if config.get('font'):
        protected.append(_resolve(project_path.parent, config['font'], 'font'))
    _require(not any(_within(path, output) for path in protected), 'output directory would contain or overwrite project inputs')
    owner = _fingerprint({'project_path': str(project_path)})
    marker = output / OUTPUT_MARKER
    if output.exists():
        _require(output.is_dir(), 'output path is not a directory')
        entries = list(output.iterdir())
        if entries:
            _require(marker.is_file(), 'non-empty output directory is not owned by this pipeline; choose a new directory')
            state = _json(marker)
            _require(state.get('owner') == owner and state.get('schema_version') == 1,
                     'output directory belongs to a different project; choose a new directory')
        for path in (output / '.p2v-cache', output / '.p2v-cache/index.json', marker,
                     output / 'video.mp4', output / 'subtitles.srt', output / 'subtitles.vtt',
                     output / 'evidence.html', output / 'build_report.json'):
            _require(not path.is_symlink(), 'pipeline output/cache path may not be a symlink')
    output.mkdir(parents=True, exist_ok=True)
    _write_json(marker, {'schema_version': 1, 'owner': owner})
    return output


def _module_hash(name):
    module = importlib.import_module(name)
    return _hash(module.__file__)


def _cached(entry, fingerprint, path, check_wave=False):
    if not isinstance(entry, dict) or entry.get('fingerprint') != fingerprint or not path.is_file() or path.is_symlink():
        return False
    try:
        if _hash(path) != entry['sha256']:
            return False
        if check_wave:
            info = _wave_info(path)
            if info['samples'] != entry['samples'] or info['sample_rate'] != entry['sample_rate']:
                return False
        return True
    except (OSError, KeyError, ValueError, wave.Error):
        return False


def _used_assets(value):
    ids = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'asset' and isinstance(item, str):
                ids.add(item)
            else:
                ids.update(_used_assets(item))
    elif isinstance(value, list):
        for item in value:
            ids.update(_used_assets(item))
    return ids


def _timestamp(seconds, separator=','):
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    whole, millis = divmod(millis, 1000)
    return f'{hours:02d}:{minutes:02d}:{whole:02d}{separator}{millis:03d}'


def _subtitles(project, timeline, output):
    srt, vtt = [], ['WEBVTT', '']
    for index, (scene, cue) in enumerate(zip(project['scenes'], timeline), 1):
        start, end = cue['start_seconds'], cue['start_seconds'] + cue['audio_duration_seconds']
        # A display cue is one authored sentence for one measured spoken sentence.
        text = scene['display_text'].replace('\r', '').strip()
        srt.extend([str(index), f'{_timestamp(start)} --> {_timestamp(end)}', text, ''])
        vtt.extend([f'{_timestamp(start, ".")} --> {_timestamp(end, ".")}', html.escape(text), ''])
    (output / 'subtitles.srt').write_text('\n'.join(srt) + '\n', encoding='utf-8')
    (output / 'subtitles.vtt').write_text('\n'.join(vtt) + '\n', encoding='utf-8')


def _evidence_page(project, report, output):
    escape = lambda value: html.escape(str(value))
    unit_map = {unit['id']: unit for unit in project['source']['units']}
    sections = []
    for claim in project['claims']:
        anchors = []
        for anchor in claim['evidence']:
            unit = unit_map[anchor['unit_id']]
            locator = unit['locator']
            place = ('line ' + str(locator['line'])) if locator['kind'] == 'text' else ('PDF page ' + str(locator['page_index'] + 1))
            anchors.append('<blockquote>' + escape(anchor['quote']) + '</blockquote><small>' +
                           escape(unit['id'] + ' · ' + place) + '</small>')
        sections.append('<section><h2>' + escape(claim['id']) + '</h2><p>' + escape(claim['text']) +
                        '</p><p class="status">Semantic review: ' + escape(claim.get('review_status', 'pending')) +
                        '</p>' + ''.join(anchors) + '</section>')
    reviews = ''.join('<li>' + escape(key) + ': ' + escape(value) + '</li>' for key, value in project['acceptance'].items())
    title = project['source'].get('metadata', {}).get('title') or 'Paper-to-video review draft'
    attribution = ''.join('<li>' + escape(key) + ': ' + escape(value['attribution']) + ' (' +
                          escape(value['rights']) + ')</li>' for key, value in project['render'].get('assets', {}).items())
    language = escape(project['project']['language'])
    text = '''<!doctype html><html lang="''' + language + '''"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + escape(title) + '''</title><style>
body{max-width:960px;margin:40px auto;padding:0 24px;background:#10151d;color:#edf2f5;font:17px/1.65 system-ui,sans-serif}
h1{font-size:30px}h2{font-size:21px;color:#62cad0}section{margin:28px 0;padding:20px;border:1px solid #344453;border-radius:12px}
blockquote{margin:16px 0;padding-left:18px;border-left:3px solid #62cad0}small,.status{color:#a7b4c0}video{width:100%;border-radius:12px}code{overflow-wrap:anywhere}
</style><h1>''' + escape(title) + '''</h1>
<p>Review draft. Automated source and media checks do not certify scientific meaning, voice quality, or aesthetics.</p>
<video controls preload="metadata" src="video.mp4"><track kind="captions" src="subtitles.vtt" srclang="''' + language + '''" label="Captions" default></video>
<p>Scope: ''' + escape(project['project'].get('scope', 'full_paper')) + ' · ' + escape(project['project'].get('selected_coverage', 'Full source')) + '''</p>
<p>Source SHA256: <code>''' + escape(project['source']['sha256']) + '</code></p><h2>Human review</h2><ul>' + reviews + '</ul>' + \
           ''.join(sections) + '<h2>Asset attribution</h2><ul>' + attribution + '</ul></html>\n'
    (output / 'evidence.html').write_text(text, encoding='utf-8')


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise ValueError('imageio-ffmpeg is required; install the documented rendering requirements') from exc


def _run_ffmpeg(arguments, timeout=900):
    result = subprocess.run([_ffmpeg(), '-nostdin', '-hide_banner', '-loglevel', 'error', *arguments],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    _require(result.returncode == 0, 'ffmpeg failed: ' + result.stderr.decode('utf-8', errors='replace')[-1600:])
    return result


def _assemble(clips, wavs, timeline, output, fps):
    """Keep rendered frames; pad only breathing pauses, never squeeze speech."""
    cache = output / '.p2v-cache'
    concat = cache / 'concat.txt'
    _require(not concat.is_symlink() and not (cache / 'timeline.wav').is_symlink()
             and not (output / 'video.pending.mp4').is_symlink(), 'temporary media output may not be a symlink')
    # Paths are our generated cache files; escape the concat demuxer's own syntax.
    concat.write_text(''.join("file '" + str(path).replace('\\', '/').replace("'", "'\\''") + "'\n" for path in clips), encoding='utf-8')
    assembled_wav = cache / 'timeline.wav'
    with wave.open(str(assembled_wav), 'wb') as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(48000)
        for wav, cue in zip(wavs, timeline):
            pcm = _run_ffmpeg(['-i', str(wav), '-map', '0:a:0', '-ac', '1', '-ar', '48000',
                               '-c:a', 'pcm_s16le', '-f', 's16le', 'pipe:1']).stdout
            target_samples = round(cue['frames'] / fps * 48000)
            _require(len(pcm) <= target_samples * 2 + 4, 'speech would be truncated by the rendered timeline')
            pcm = pcm[:target_samples * 2]
            destination.writeframesraw(pcm)
            destination.writeframesraw(b'\0' * (target_samples * 2 - len(pcm)))
    pending = output / 'video.pending.mp4'
    duration = sum(item['frames'] for item in timeline) / fps
    _run_ffmpeg(['-y', '-f', 'concat', '-safe', '0', '-i', str(concat), '-i', str(assembled_wav),
                 '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                 '-ar', '48000', '-t', f'{duration:.9f}', '-movflags', '+faststart', str(pending)])
    os.replace(pending, output / 'video.mp4')
    return _decode_video(output / 'video.mp4', sum(item['frames'] for item in timeline))


def _decode_video(path, expected_frames):
    result = _run_ffmpeg(['-i', str(path), '-map', '0:v:0', '-map', '0:a:0',
                          '-progress', 'pipe:1', '-f', 'null', '-'])
    progress = result.stdout.decode('utf-8', errors='replace')
    frames = [int(value) for value in re.findall(r'^frame=(\d+)\s*$', progress, flags=re.MULTILINE)]
    _require(frames and frames[-1] == expected_frames,
             'decoded frame count does not match the measured scene timeline')
    return {'decoded': True, 'decoded_frames': frames[-1], 'audio_decode': True}


def build(project_path, output_dir, width=None, fps=None, resume=False,
          audio_fn=None, render_fn=None, assemble_fn=None, visual_validator=None, audio_config_path=None):
    started = time.monotonic()
    validation = validate_project(project_path, width, fps, visual_validator, audio_config_path)
    _require(validation['build_ready'], '; '.join(validation['errors']))
    project, path = load_project(project_path)
    config = _override_audio(_render_config(project, width, fps), audio_config_path)
    runtime = copy.deepcopy(project)
    runtime['_base_dir'] = str(path.parent)
    runtime['render'] = config
    runtime['project'].pop('render', None)
    output = _prepare_output(path, runtime, output_dir)
    cache = output / '.p2v-cache'
    cache.mkdir(exist_ok=True)
    index_path = cache / 'index.json'
    try:
        old_index = _json(index_path) if resume and index_path.is_file() else {}
        old = old_index.get('scenes', {}) if old_index.get('schema_version') == CACHE_SCHEMA else {}
        _require(isinstance(old, dict), 'invalid cache index')
    except (OSError, TypeError, ValueError):
        old = {}
    if audio_fn is None:
        audio_fn = importlib.import_module('p2v.audio').synthesize
        audio_version = _module_hash('p2v.audio')
    else:
        audio_version = 'injected-test-provider'
    if render_fn is None:
        render_fn = importlib.import_module('p2v.renderer').render_scene
        renderer_version = _module_hash('p2v.renderer')
    else:
        renderer_version = 'injected-test-provider'
    assemble_fn = _assemble if assemble_fn is None else assemble_fn
    assets = validation['automated_checks']['assets']
    timeline, clips, wavs, index = [], [], [], {}
    elapsed_frames = 0
    for original_scene in project['scenes']:
        scene = copy.deepcopy(original_scene)
        scene_id = scene['id']
        scene_dir = cache / hashlib.sha256(scene_id.encode('utf-8')).hexdigest()[:24]
        _require(not scene_dir.is_symlink(), 'scene cache directory may not be a symlink')
        scene_dir.mkdir(exist_ok=True)
        wav, clip = scene_dir / 'narration.wav', scene_dir / 'clip.mp4'
        _require(not wav.is_symlink() and not clip.is_symlink(), 'scene cache files may not be symlinks')
        audio_config, input_hashes = _audio_config(config, scene, path.parent)
        fingerprint_config = {key: value for key, value in audio_config.items() if key not in ('path', 'model_path', 'voices_path')}
        audio_key = _fingerprint({'text': scene['spoken_text'], 'configuration': fingerprint_config,
                                  'dependencies': input_hashes, 'implementation': audio_version})
        previous = old.get(scene_id, {})
        reused_audio = bool(resume and _cached(previous.get('audio'), audio_key, wav, check_wave=True))
        if not reused_audio:
            audio_fn(scene['spoken_text'], wav, audio_config)
        wave_info = _wave_info(wav)
        audio_digest = _hash(wav)
        index[scene_id] = {'audio': {'fingerprint': audio_key, 'sha256': audio_digest,
                                   'samples': wave_info['samples'], 'sample_rate': wave_info['sample_rate'],
                                   'duration_seconds': wave_info['duration_seconds']}}
        _write_json(index_path, {'schema_version': CACHE_SCHEMA, 'scenes': {**old, **index}})
        audio_duration = wave_info['duration_seconds']
        frames = math.ceil((audio_duration + config['pause_seconds']) * config['fps'] - 1e-8)
        duration = frames / config['fps']
        scene['_audio_duration'] = audio_duration
        used = _used_assets(scene['visual'])
        _require(used.issubset(set(assets)), 'visual references unconfigured asset')
        visual_config = {key: value for key, value in config.items() if key not in ('audio', 'assets', 'pause_seconds')}
        visual_scene = {key: value for key, value in scene.items()
                        if key not in ('spoken_text', 'claim_ids', 'visual_intent', 'start_seconds', 'end_seconds', 'audio_path')}
        visible_project = {key: value for key, value in project['project'].items()
                           if key not in ('render', 'pronunciations', 'target_seconds', 'selected_coverage', 'scope')}
        clip_key = _fingerprint({'scene': visual_scene, 'config': visual_config, 'duration': duration,
                                 'project': visible_project, 'source_metadata': project['source'].get('metadata'),
                                 'source_provenance': project['source'].get('provenance'),
                                 'assets': {key: assets[key] for key in used | ({'_font'} if '_font' in assets else set())},
                                 'implementation': renderer_version})
        reused_clip = bool(resume and _cached(previous.get('render'), clip_key, clip))
        if not reused_clip:
            result = render_fn(runtime, scene, clip, duration, config['width'], config['fps'])
            _require(isinstance(result, dict) and result.get('frames') == frames, 'renderer returned a different frame count')
            _require(clip.is_file() and clip.stat().st_size > 0, 'renderer did not produce a scene clip')
        clip_digest = _hash(clip)
        index[scene_id]['render'] = {'fingerprint': clip_key, 'sha256': clip_digest, 'frames': frames}
        _write_json(index_path, {'schema_version': CACHE_SCHEMA, 'scenes': {**old, **index}})
        cue = {'id': scene_id, 'start_seconds': elapsed_frames / config['fps'],
               'end_seconds': (elapsed_frames + frames) / config['fps'], 'frames': frames,
               'audio_duration_seconds': audio_duration, 'pause_duration_seconds': duration - audio_duration,
               'audio_sha256': audio_digest, 'clip_sha256': clip_digest,
               'audio_reused': reused_audio, 'clip_reused': reused_clip}
        timeline.append(cue)
        elapsed_frames += frames
        clips.append(clip)
        wavs.append(wav)
    decoded = assemble_fn(clips, wavs, timeline, output, config['fps'])
    _require(decoded.get('decoded') is True and decoded.get('audio_decode') is True,
             'assembled audiovisual output was not fully decoded')
    _require(decoded.get('decoded_frames') == elapsed_frames, 'assembled output has incorrect frame count')
    _subtitles(project, timeline, output)
    report = {'schema_version': 1, 'pipeline_version': __version__,
              'project_sha256': _hash(path), 'source_sha256': project['source']['sha256'],
              'scope': project['project'].get('scope', 'full_paper'),
              'selected_coverage': project['project'].get('selected_coverage'),
              'duration_seconds': elapsed_frames / config['fps'], 'frames': elapsed_frames,
              'width': config['width'], 'fps': config['fps'], 'content_led_timing': True,
              'audio_mode': config['audio']['engine'],
              'narration_present': config['audio']['engine'] != 'silence',
              'timing_basis': 'authored_silent_preview' if config['audio']['engine'] == 'silence' else 'measured_audio',
              'automated_checks': {**validation['automated_checks'], 'audiovisual_decode': decoded},
              'automated_passed': True, 'scientific_guarantee': False,
              'human_review': copy.deepcopy(project['acceptance']), 'pending': validation['pending'],
              'cache': {'audio_reused': sum(item['audio_reused'] for item in timeline),
                        'clips_reused': sum(item['clip_reused'] for item in timeline),
                        'audio_built': sum(not item['audio_reused'] for item in timeline),
                        'clips_built': sum(not item['clip_reused'] for item in timeline)},
              'scenes': timeline, 'elapsed_seconds': round(time.monotonic() - started, 3),
              'note': ('Silent visual preview with authored durations; no narration or pronunciation review is implied.'
                       if config['audio']['engine'] == 'silence' else
                       'Measured draft output only. Human source/scientific/audio/visual approval is never set by this build.')}
    _evidence_page(runtime, report, output)
    report['outputs'] = {name: {'sha256': _hash(output / name), 'bytes': (output / name).stat().st_size}
                         for name in ('video.mp4', 'subtitles.srt', 'subtitles.vtt', 'evidence.html')}
    _write_json(index_path, {'schema_version': CACHE_SCHEMA, 'scenes': index})
    _write_json(output / 'build_report.json', report)
    return report


def doctor():
    checks = {'python': {'version': sys.version.split()[0],
                         'supported': sys.version_info[:2] == (3, 12),
                         'required': '3.12'}}
    for name in ('PIL', 'imageio_ffmpeg'):
        try:
            module = importlib.import_module(name)
            checks[name] = {'installed': True, 'version': getattr(module, '__version__', 'unknown')}
        except ImportError:
            checks[name] = {'installed': False}
    try:
        result = subprocess.run([_ffmpeg(), '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        version_lines = result.stdout.decode('utf-8', errors='replace').splitlines()
        checks['ffmpeg'] = {'available': result.returncode == 0,
                            'version': version_lines[0] if version_lines else 'unavailable'}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        checks['ffmpeg'] = {'available': False, 'error': str(exc)}
    try:
        checks['audio'] = importlib.import_module('p2v.audio').doctor()
    except (ImportError, OSError, ValueError) as exc:
        checks['audio'] = {'available': False, 'error': str(exc)}
    return {'ok': checks['python']['supported'] and all(checks[name]['installed'] for name in ('PIL', 'imageio_ffmpeg'))
                  and checks.get('ffmpeg', {}).get('available', False),
            'checks': checks, 'note': 'No models, fonts, voices, or packages are downloaded automatically. Import-audio builds do not require synthesis models.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor')
    initialize = commands.add_parser('init')
    initialize.add_argument('source', type=Path)
    initialize.add_argument('output', type=Path)
    initialize.add_argument('--format', choices=('reader-card', 'text'), required=True)
    initialize.add_argument('--article-type', choices=_contract_module().TYPES, default='unknown')
    initialize.add_argument('--coverage', choices=('full', 'abstract', 'partial', 'unknown'), default='unknown')
    initialize.add_argument('--language', default='zh-CN')
    initialize.add_argument('--seconds', type=float, default=None)
    validate = commands.add_parser('validate')
    validate.add_argument('project', type=Path)
    validate.add_argument('--audio-config', type=Path)
    make = commands.add_parser('build')
    make.add_argument('project', type=Path)
    make.add_argument('--output-dir', '--output', dest='output_dir', type=Path, required=True)
    make.add_argument('--width', type=int)
    make.add_argument('--fps', type=int)
    make.add_argument('--resume', action='store_true', help='Reuse byte-verified unchanged scene audio and visual clips.')
    make.add_argument('--audio-config', type=Path, help='Local JSON audio override; its file paths resolve from the override file.')
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            result = doctor()
        elif args.command == 'init':
            contract = _contract_module()
            project = contract.create_project(args.source, args.format, args.article_type,
                                               args.coverage, args.language, args.seconds)
            project['source']['path'] = os.path.relpath(args.source.resolve(), args.output.resolve().parent).replace(os.sep, '/')
            result = contract.validate(project)
            _require(result['contract_valid'], '; '.join(result['errors']))
            contract.write_new(args.output, project)
            result['ok'] = True
            result['note'] = 'Input adapter complete; the Agent must prepare and review evidence, narration, and supported visual scenes.'
        elif args.command == 'validate':
            result = validate_project(args.project, audio_config_path=args.audio_config)
        else:
            report = build(args.project, args.output_dir, args.width, args.fps, args.resume, audio_config_path=args.audio_config)
            result = {'ok': True, 'output_directory': str(args.output_dir.resolve()),
                      'duration_seconds': report['duration_seconds'], 'cache': report['cache'],
                      'human_review': report['human_review'], 'automated_passed': report['automated_passed']}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result['ok'] else 1
    except (OSError, ValueError, KeyError, TypeError, ImportError, AttributeError, wave.Error, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'command': args.command, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
