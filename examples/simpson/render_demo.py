"""Render the bundled synthetic comparison; no PDF, network or TTS service.

The example's authored visual schedule is not measured speech alignment.
Install requirements-demo.txt. Run from any working directory.
"""
import argparse
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
DURATION = 48
BG = '#10151f'
WHITE = '#eef2f6'
MUTED = '#aab7c7'
A_COLOR = '#5cc9ce'
B_COLOR = '#f1c56c'
EASY = '#aa9ed7'
HARD = '#536378'
TIMES = (0, 5, 14, 23, 35, 44, 48)


@lru_cache(maxsize=48)
def font_at(size):
    from PIL import ImageFont
    return ImageFont.load_default(size=size)


def load_data(path=HERE / 'data.json'):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or data.get('provenance', {}).get('synthetic') is not True:
        raise ValueError('The example requires labelled synthetic data, schema_version 1.')
    groups = data.get('groups', [])
    if {g.get('id') for g in groups} != {'easy', 'hard'} or len(groups) != 2:
        raise ValueError('This narrow example needs exactly easy and hard groups.')
    for group in groups:
        for name in ('A', 'B'):
            values = group[name]
            n, k = values['trials'], values['successes']
            if type(n) is not int or type(k) is not int or not 0 <= k <= n or n <= 0:
                raise ValueError('Counts must be integers with 0 <= successes <= positive trials.')
    weights = data['standardization']['weights']
    if set(weights) != {'easy', 'hard'} or any(type(w) not in (int, float) or not math.isfinite(w) or w < 0 for w in weights.values()) or not math.isclose(sum(weights.values()), 1):
        raise ValueError('Common group weights must be nonnegative and sum to one.')
    return data


def calculate(data):
    groups = {g['id']: g for g in data['groups']}
    rates = {gid: {name: group[name]['successes'] / group[name]['trials'] for name in ('A', 'B')} for gid, group in groups.items()}
    totals = {name: {key: sum(g[name][key] for g in groups.values()) for key in ('successes', 'trials')} for name in ('A', 'B')}
    pooled = {name: v['successes'] / v['trials'] for name, v in totals.items()}
    mixes = {name: groups['easy'][name]['trials'] / totals[name]['trials'] for name in ('A', 'B')}
    standardized = {name: sum(rates[gid][name] * weight for gid, weight in data['standardization']['weights'].items()) for name in ('A', 'B')}
    return {'groups': groups, 'rates': rates, 'totals': totals, 'pooled': pooled, 'easy_mix': mixes, 'standardized': standardized}


def parse_srt(path=HERE / 'subtitles.en.srt'):
    def seconds(value):
        h, m, s = value.replace(',', '.').split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    blocks = []
    for block in Path(path).read_text(encoding='utf-8-sig').strip().split('\n\n'):
        lines = block.splitlines()
        start, end = lines[1].split(' --> ')
        blocks.append({'start': seconds(start), 'end': seconds(end), 'lines': lines[2:]})
    if len(blocks) != 6 or any(b['start'] != TIMES[i] or b['end'] != TIMES[i + 1] for i, b in enumerate(blocks)):
        raise ValueError('Subtitles must match the six authored scene intervals.')
    return blocks


def verify_inputs(data, result, captions):
    """Reject stale explanations when the bundled counts or weights change."""
    if not all(result['rates'][gid]['B'] > result['rates'][gid]['A'] for gid in ('easy', 'hard')) or not result['pooled']['A'] > result['pooled']['B']:
        raise ValueError('These counts do not support the example reversal.')
    expected = {'easy': {'A': .90, 'B': .95}, 'hard': {'A': .10, 'B': .20}}
    if any(not math.isclose(result['rates'][g][n], expected[g][n]) for g in expected for n in ('A', 'B')) or not math.isclose(result['pooled']['A'], 91 / 110) or not math.isclose(result['pooled']['B'], 39 / 120) or not math.isclose(result['standardized']['A'], .50) or not math.isclose(result['standardized']['B'], .575):
        raise ValueError('Data changed: revise the article, evidence and captions together before rendering.')
    evidence = json.loads((HERE / 'evidence_map.json').read_text(encoding='utf-8'))
    source_lines = (HERE / 'article.txt').read_text(encoding='utf-8').splitlines()
    for claim in evidence['claims']:
        for anchor in claim['evidence']:
            line = int(anchor['unit_id'].removeprefix('line_'))
            if line < 1 or line > len(source_lines) or anchor['quote'] not in source_lines[line - 1]:
                raise ValueError('A source quote is missing or changed.')
    for i, scene in enumerate(evidence['scenes']):
        if scene['start_seconds'] != captions[i]['start'] or scene['end_seconds'] != captions[i]['end']:
            raise ValueError('Evidence scene timing does not match the captions.')


def ease(t):
    t = max(0, min(1, t))
    return t * t * (3 - 2 * t)


def percent(value):
    return f'{value * 100:.1f}'.rstrip('0').rstrip('.') + '%'


class Canvas:
    """A fixed design canvas scaled uniformly; built-in font, no machine font paths."""
    def __init__(self, width):
        from PIL import Image, ImageDraw
        self.scale = width / 1920 * 1.5
        self.image = Image.new('RGB', (round(1920 * self.scale), round(1080 * self.scale)), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.width = width

    def font(self, size):
        return font_at(round(size * self.scale))

    def text(self, x, y, text, size, fill=WHITE, anchor='lt'):
        self.draw.text((x * self.scale, y * self.scale), text, font=self.font(size), fill=fill, anchor=anchor)

    def line(self, points, fill, width=2):
        self.draw.line([(x * self.scale, y * self.scale) for x, y in points], fill=fill, width=max(1, round(width * self.scale)), joint='curve')

    def round_rect(self, box, radius, fill):
        self.draw.rounded_rectangle(tuple(v * self.scale for v in box), radius=radius * self.scale, fill=fill)

    def ellipse(self, box, fill):
        self.draw.ellipse(tuple(v * self.scale for v in box), fill=fill)

    def sector(self, box, start, end, fill):
        self.draw.pieslice(tuple(v * self.scale for v in box), start=start, end=end, fill=fill)

    def finish(self):
        from PIL import Image
        return self.image.resize((self.width, self.width * 9 // 16), Image.Resampling.LANCZOS)


def header(c):
    c.text(108, 64, 'Paper to Video', 27, MUTED)


def pair(c, result, group_id, age):
    title = 'B leads in the easy group' if group_id == 'easy' else 'B leads in the hard group, too'
    c.text(960, 176, title, 61, anchor='mt')
    c.text(435, 289, 'Success rate', 31, MUTED)
    c.line([(435, 380), (1475, 380)], '#354152', 2)
    for tick in (0, .5, 1):
        x = 435 + 1040 * tick
        c.line([(x, 369), (x, 391)], '#657487', 2)
        c.text(x, 341, percent(tick), 25, MUTED, 'mt')
    grow = ease((age - .5) / 1.8)
    group = result['groups'][group_id]
    for i, (name, color) in enumerate((('A', A_COLOR), ('B', B_COLOR))):
        y = 473 + i * 208
        rate = result['rates'][group_id][name]
        c.text(308, y + 30, name, 69, color, 'mm')
        c.round_rect((435, y, 1475, y + 68), 17, '#202b39')
        end = 435 + 1040 * rate * grow
        if end > 443:
            c.round_rect((435, y, end, y + 68), min(17, (end - 435) / 2), color)
        if grow >= .99:
            c.text(1530, y + 33, percent(rate), 61, color, 'lm')
        values = group[name]
        count_label = 'success' if values['successes'] == 1 else 'successes'
        c.text(435, y + 92, f'{values["successes"]} {count_label} / {values["trials"]} trials', 32, MUTED)


def donut(c, x, y, easy_fraction, age):
    radius = 147
    box = (x - radius, y - radius, x + radius, y + radius)
    c.ellipse(box, HARD)
    c.sector(box, -90, -90 + 360 * easy_fraction * ease(age / 1.3), EASY)
    c.ellipse((x - 107, y - 107, x + 107, y + 107), BG)


def mixtures(c, data, result, age, common=False):
    title = 'Use the same group weights' if common else 'Different mixes reverse the average'
    c.text(960, 176, title, 59, anchor='mt')
    c.ellipse((778, 290, 798, 310), EASY)
    c.text(815, 281, 'Easy', 30, MUTED)
    c.ellipse((994, 290, 1014, 310), HARD)
    c.text(1031, 281, 'Hard', 30, MUTED)
    for name, color, x in (('A', A_COLOR, 540), ('B', B_COLOR, 1380)):
        mix = data['standardization']['weights']['easy'] if common else result['easy_mix'][name]
        donut(c, x, 511, mix, age)
        c.text(x, 496, name, 73, color, 'mm')
        c.text(x, 550, '50 : 50' if common else f'{mix * 100:.0f}% easy', 31, MUTED, 'mm')
        if age > 1.3:
            value = result['standardized'][name] if common else result['pooled'][name]
            c.text(x, 707, percent(value), 88, color, 'mm')
            if common:
                c.text(x, 792, 'Common 50:50 weighted rate', 30, MUTED, 'mm')
            else:
                totals = result['totals'][name]
                c.text(x, 792, f'{totals["successes"]} successes / {totals["trials"]} trials', 30, MUTED, 'mm')
    c.text(960, 712, 'vs', 34, MUTED, 'mm')


def intro(c, age, result):
    c.text(960, 225, 'Can averages flip', 88, anchor='mt')
    c.text(960, 332, 'a comparison?', 88, anchor='mt')
    for name, color, x in (('A', A_COLOR, 470), ('B', B_COLOR, 1150)):
        c.text(x - 68, 643, name, 63, color, 'mm')
        total = result['totals'][name]['trials']
        easy_trials = result['groups']['easy'][name]['trials']
        for j in range(total):
            px, py = x + j % 10 * 29, 536 + j // 10 * 23
            if age >= .35 + j / total * 1.8:
                c.ellipse((px - 7, py - 7, px + 7, py + 7), EASY if j < easy_trials else HARD)
    c.text(960, 865, 'Each dot is one constructed trial; color marks its group.', 32, MUTED, 'mm')


def closing(c, result):
    c.text(960, 190, 'Check the groups', 83, anchor='mt')
    c.text(960, 290, 'before the average.', 83, anchor='mt')
    items = [('Easy', 'easy', 390), ('Hard', 'hard', 960), ('Same weights', None, 1530)]
    for label, gid, x in items:
        c.text(x, 490, label, 38, MUTED, 'mm')
        values = result['rates'][gid] if gid else result['standardized']
        c.text(x, 585, percent(values['A']), 66, A_COLOR, 'mm')
        c.text(x, 690, percent(values['B']), 66, B_COLOR, 'mm')
    c.text(960, 819, 'A', 29, A_COLOR, 'mm')
    c.text(1030, 819, '/', 29, MUTED, 'mm')
    c.text(1100, 819, 'B', 29, B_COLOR, 'mm')


def scene_image(t, width, data, result):
    index = next(i for i in range(6) if TIMES[i] <= t < TIMES[i + 1])
    age = t - TIMES[index]
    c = Canvas(width)
    header(c)
    if index == 0:
        intro(c, age, result)
    elif index in (1, 2):
        pair(c, result, 'easy' if index == 1 else 'hard', age)
    elif index in (3, 4):
        mixtures(c, data, result, age, common=index == 4)
    else:
        closing(c, result)
    return c.finish(), index


def render_frame(t, width, data, result, captions):
    from PIL import Image, ImageDraw
    image, index = scene_image(t, width, data, result)
    age = t - TIMES[index]
    # Fade each outgoing scene toward the background. Text values never
    # interpolate between data categories, preventing fictional intermediate rates.
    left = TIMES[index + 1] - t
    opacity = min(ease(age / .45), ease(left / .45))
    if opacity < 1:
        image = Image.blend(Image.new('RGB', image.size, BG), image, opacity)
    draw = ImageDraw.Draw(image)
    scale = width / 1920
    draw.text((1812 * scale, 64 * scale), 'SYNTHETIC EXAMPLE', font=font_at(round(25 * scale)), fill=MUTED, anchor='rt')
    font = font_at(round(42 * scale))
    lines = captions[index]['lines']
    y = (968 - (len(lines) - 1) * 25) * scale
    for i, text in enumerate(lines):
        draw.text((width / 2, y + i * 51 * scale), text, font=font, fill=WHITE, anchor='mm')
    draw.text((108 * scale, 1049 * scale), 'Constructed counts - not experimental data', font=font_at(round(21 * scale)), fill=MUTED, anchor='lb')
    return image


def check_audio(ffmpeg, path):
    run = subprocess.run([ffmpeg, '-hide_banner', '-i', str(path), '-f', 'null', '-'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', run.stderr)
    if run.returncode or not match:
        raise ValueError('Audio could not be fully decoded, or its duration is unknown.')
    h, m, s = match.groups()
    duration = int(h) * 3600 + int(m) * 60 + float(s)
    if not DURATION - .05 <= duration <= DURATION + .25:
        raise ValueError('Audio must follow the 48-second authored schedule. No automatic retiming is performed.')
    return duration


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('outputs/demo.mp4'))
    parser.add_argument('--width', type=int, default=1920, choices=(1280, 1920, 2560))
    parser.add_argument('--fps', type=int, default=24, choices=(12, 24, 30))
    parser.add_argument('--audio', type=Path, help='Optional authorized narration already matched to the 48-second schedule.')
    parser.add_argument('--stills-dir', type=Path)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    companions = [output, output.with_suffix('.poster.png'), output.with_suffix('.srt'), output.with_suffix('.report.json')]
    if any(p.exists() for p in companions):
        parser.error('An output or companion already exists. Choose a new output name to preserve earlier results.')
    if output.suffix.lower() != '.mp4':
        parser.error('--output must end in .mp4')
    if args.audio and not args.audio.is_file():
        parser.error('--audio does not name an existing file')
    try:
        import imageio_ffmpeg
        import PIL
        data = load_data()
        result = calculate(data)
        captions = parse_srt()
        verify_inputs(data, result, captions)
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        audio_duration = check_audio(ffmpeg, args.audio) if args.audio else None
    except (ImportError, ValueError) as exc:
        parser.error(str(exc))
    output.parent.mkdir(parents=True, exist_ok=True)
    frames = DURATION * args.fps
    with tempfile.TemporaryDirectory(prefix='p2v-demo-', dir=output.parent) as temp:
        silent = Path(temp) / 'silent.mp4'
        writer = imageio_ffmpeg.write_frames(str(silent), (args.width, args.width * 9 // 16), fps=args.fps, codec='libx264', pix_fmt_in='rgb24', pix_fmt_out='yuv420p', macro_block_size=1, ffmpeg_log_level='error', output_params=['-crf', '18', '-preset', 'medium', '-movflags', '+faststart'])
        writer.send(None)
        try:
            for i in range(frames):
                frame = render_frame(i / args.fps, args.width, data, result, captions)
                writer.send(frame.tobytes())
                if i % (args.fps * 8) == 0:
                    print(f'Rendered {i // args.fps}/{DURATION} seconds', flush=True)
        finally:
            writer.close()
        if args.audio:
            run = subprocess.run([ffmpeg, '-v', 'error', '-i', str(silent), '-i', str(args.audio.resolve()), '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-t', str(DURATION), '-movflags', '+faststart', '-n', str(output)], capture_output=True)
            if run.returncode:
                raise RuntimeError('Optional audio mux failed. No source audio was changed.')
        else:
            shutil.copyfile(silent, output)
    render_frame(30, args.width, data, result, captions).save(output.with_suffix('.poster.png'))
    shutil.copyfile(HERE / 'subtitles.en.srt', output.with_suffix('.srt'))
    if args.stills_dir:
        args.stills_dir.mkdir(parents=True, exist_ok=True)
        for t in (3, 9, 18, 30, 40, 46):
            render_frame(t, args.width, data, result, captions).save(args.stills_dir / f'{t:02d}s.png')
    report = {'synthetic': True, 'duration_seconds': DURATION, 'fps': args.fps, 'frames_written': frames, 'width': args.width, 'height': args.width * 9 // 16, 'versions': {'python': sys.version.split()[0], 'Pillow': PIL.__version__, 'imageio_ffmpeg': imageio_ffmpeg.__version__}, 'font': 'Pillow built-in scalable font; no external font file', 'data_sha256': hashlib.sha256((HERE / 'data.json').read_bytes()).hexdigest(), 'input_checks': 'passed', 'pooled': result['pooled'], 'common_weights': data['standardization']['weights'], 'standardized': result['standardized'], 'audio': {'present': bool(args.audio), 'decoded_duration': audio_duration, 'timing_basis': 'authored_visual_schedule', 'word_alignment': 'not_performed'}, 'checks_not_performed': ['independent scientific review', 'arbitrary-paper generation', 'cross-platform execution', 'human assessment of supplied audio'], 'video_sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
    output.with_suffix('.report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Created {output.name}: {DURATION}s, {args.width}x{args.width * 9 // 16}, {args.fps}fps.', flush=True)


if __name__ == '__main__':
    main()
