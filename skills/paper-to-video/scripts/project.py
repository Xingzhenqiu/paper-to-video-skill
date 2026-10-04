"""Portable, standard-library input adapter and evidence contract (Python 3.10+).

Does not generate claims, certify science, render videos, or call cloud services.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

TYPES = ('unknown', 'experimental', 'review', 'clinical', 'engineering', 'theoretical', 'opinion')
ROUTES = {
    'unknown': ['classify_before_storyboarding'],
    'experimental': ['question', 'design', 'results', 'limits'],
    'review': ['question', 'evidence_map', 'disagreements', 'limits'],
    'clinical': ['population', 'comparison', 'endpoints', 'uncertainty'],
    'engineering': ['task', 'method', 'evaluation', 'limits'],
    'theoretical': ['assumptions', 'definitions', 'reasoning', 'limits'],
    'opinion': ['question', 'argument', 'counterargument', 'limits'],
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def check_locator(locator):
    require(isinstance(locator, dict), 'locator must be an object')
    if locator.get('kind') == 'text':
        require(type(locator.get('line')) is int and locator['line'] > 0, 'invalid text line')
    elif locator.get('kind') == 'pdf':
        require(type(locator.get('page_index')) is int and locator['page_index'] >= 0, 'invalid PDF page')
        bbox = locator.get('bbox')
        require(isinstance(bbox, list) and len(bbox) == 4 and all(type(x) in (int, float) and math.isfinite(x) for x in bbox), 'invalid PDF bbox')
        require(bbox[2] > bbox[0] and bbox[3] > bbox[1], 'empty or inverted PDF bbox')
    else:
        raise ValueError('unsupported locator kind')


def create_project(source, fmt, article_type, coverage, language, duration):
    source = Path(source)
    require(article_type in TYPES, 'unsupported article_type')
    require(fmt in ('reader-card', 'text'), 'unsupported input format')
    require(duration is None or (math.isfinite(duration) and duration > 0), 'duration must be null or positive and finite')
    raw = source.read_bytes()
    units, figures, warnings = [], [], []
    upstream_issues=[]
    if fmt == 'reader-card':
        card = read_json(source)
        require(isinstance(card, dict), 'Reader card must be an object')
        quality=card.get('quality', {})
        require(isinstance(quality, dict), 'Reader quality must be an object')
        upstream_issues=quality.get('issues', [])
        require(isinstance(upstream_issues, list) and all(nonempty(x) for x in upstream_issues), 'Reader issues must be a list of strings')
        paragraphs = card.get('paragraphs', [])
        require(isinstance(paragraphs, list), 'paragraphs must be a list')
        for paragraph in paragraphs:
            require(isinstance(paragraph, dict), 'paragraph must be an object')
            require(nonempty(paragraph.get('id')) and nonempty(paragraph.get('text')), 'paragraph needs id/text')
            page = paragraph.get('page')
            bbox = paragraph.get('bbox')
            require(type(page) is int and page >= 0, 'paragraph needs a zero-based PDF page')
            require(isinstance(bbox, list) and len(bbox) == 4 and all(type(x) in (int, float) and math.isfinite(x) for x in bbox), 'paragraph needs a finite bbox')
            units.append({'id': paragraph['id'], 'text': paragraph['text'],
                          'locator': {'kind': 'pdf', 'page_index': page, 'bbox': bbox}})
        raw_figures = card.get('figures', [])
        require(isinstance(raw_figures, list), 'figures must be a list')
        for figure in raw_figures:
            require(isinstance(figure, dict) and nonempty(figure.get('id')), 'figure needs id')
            # Asset paths and personal metadata deliberately stay in the private Reader output.
            figures.append({'id': figure['id'], 'caption': figure.get('caption', ''),
                            'page_index': figure.get('page'), 'clip': figure.get('clip'),
                            'caption_page_index': figure.get('caption_page',figure.get('page')),
                            'caption_bbox': figure.get('caption_bbox'),
                            'review_status': 'pending'})
        warnings.append('Reader output imported; original PDF and figure assets still require visual review.')
        meta = card.get('meta', {})
        require(isinstance(meta, dict), 'meta must be an object')
        metadata = {key: meta.get(key) for key in ('title', 'doi', 'year')}
    else:
        text = raw.decode('utf-8-sig')
        # Lines preserve exact positions even for Chinese text without sentence punctuation.
        units = [{'id': f'line_{i}', 'text': line, 'locator': {'kind': 'text', 'line': i}}
                 for i, line in enumerate(text.splitlines(), 1) if line.strip()]
        metadata = {'title': None, 'doi': None, 'year': None}
        warnings.append('Plain text imported; completeness and lost figures/formulas require review.')
    require(units, 'no usable text: OCR or a fuller source is required')
    require(len({x['id'] for x in units}) == len(units), 'duplicate source unit IDs')
    return {
        'schema_version': 1,
        'project': {'article_type': article_type, 'language': language, 'target_seconds': duration,
                    'audience': None, 'use': 'private', 'pronunciations': {}},
        'source': {'id': 'source_1', 'format': fmt, 'sha256': hashlib.sha256(raw).hexdigest(),
                   'coverage': coverage, 'rights': 'unknown', 'metadata': metadata,
                   'units': units, 'figures': figures, 'upstream_issues': upstream_issues,
                   'issue_reviews': []},
        'route': ROUTES[article_type], 'claims': [], 'scenes': [],
        'warnings': warnings,
        'acceptance': {'source_review': 'pending', 'scientific_review': 'pending',
                       'audio_review': 'not_run', 'visual_review': 'not_run', 'timing_review': 'not_run'},
    }


def validate(project):
    """Check source references and readiness; never equate schema validity with accuracy."""
    errors, pending = [], []
    try:
        require(isinstance(project, dict), 'project must be an object')
        require(project.get('schema_version') == 1, 'unsupported schema_version')
        config, source = project['project'], project['source']
        require(config['article_type'] in TYPES, 'unsupported article_type')
        seconds = config['target_seconds']
        require(seconds is None or (type(seconds) in (int, float) and math.isfinite(seconds) and seconds > 0), 'invalid target_seconds')
        require(nonempty(config['language']), 'missing language')
        require(source['coverage'] in ('full', 'abstract', 'partial', 'unknown'), 'invalid coverage')
        issues=source.get('upstream_issues', [])
        require(isinstance(issues,list) and all(nonempty(x) for x in issues), 'invalid upstream issues')
        reviews=source.get('issue_reviews', [])
        require(isinstance(reviews,list), 'invalid issue reviews')
        resolved=set()
        for review in reviews:
            require(review['code'] in issues and nonempty(review['reason']), 'issue review needs known code and reason')
            if review.get('status')=='verified': resolved.add(review['code'])
        for issue in issues:
            if issue != 'license_not_found_in_pdf' and issue not in resolved:
                pending.append('upstream extraction issue: '+issue)
        require(nonempty(source['id']), 'missing source id')
        fingerprint = source['sha256']
        require(isinstance(fingerprint, str) and len(fingerprint) == 64 and all(c in '0123456789abcdef' for c in fingerprint), 'invalid source hash')
        units = source['units']
        require(isinstance(units, list) and bool(units), 'no source units')
        unit_map = {}
        for unit in units:
            require(nonempty(unit['id']) and unit['id'] not in unit_map, 'invalid or duplicate unit id')
            require(nonempty(unit['text']) and bool(unit['locator']), 'missing source text/locator')
            check_locator(unit['locator'])
            unit_map[unit['id']] = unit
        claims, scenes = project['claims'], project['scenes']
        require(isinstance(claims, list) and isinstance(scenes, list), 'claims/scenes must be lists')
        claim_ids, scene_ids = set(), set()
        for claim in claims:
            require(nonempty(claim['id']) and claim['id'] not in claim_ids, 'invalid or duplicate claim id')
            claim_ids.add(claim['id'])
            require(nonempty(claim['text']), 'empty claim')
            evidence = claim['evidence']
            require(isinstance(evidence, list) and bool(evidence), 'claim without evidence')
            for anchor in evidence:
                require(anchor['unit_id'] in unit_map, 'dangling evidence reference')
                require(nonempty(anchor['quote']) and anchor['quote'] in unit_map[anchor['unit_id']]['text'], 'evidence quote not found in source unit')
            if claim.get('review_status') != 'verified':
                pending.append('claim requires semantic review: ' + claim['id'])
        for scene in scenes:
            require(nonempty(scene['id']) and scene['id'] not in scene_ids, 'invalid or duplicate scene id')
            scene_ids.add(scene['id'])
            require(nonempty(scene['display_text']) and nonempty(scene['spoken_text']), 'scene needs display_text/spoken_text')
            refs = scene['claim_ids']
            require(isinstance(refs, list) and bool(refs) and all(ref in claim_ids for ref in refs), 'scene has missing claim references')
            require(nonempty(scene['visual_intent']), 'scene needs visual_intent')
        if config['article_type'] == 'unknown':
            pending.append('classify article type')
        if source['coverage'] != 'full':
            pending.append('limited/unknown source coverage; full-paper production blocked')
        if not claims or not scenes:
            pending.append('prepare evidence-backed claims and scenes')
        if project['acceptance'].get('source_review') != 'verified':
            pending.append('review extraction against original source')
        if project['acceptance'].get('scientific_review') != 'verified':
            pending.append('review scientific meaning, comparisons and limitations')
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        errors.append(str(exc))
    return {'contract_valid': not errors, 'evidence_ready': not errors and not pending,
            'video_ready': False, 'errors': errors, 'pending': pending,
            'note': 'References and quotes are structural checks, not independent scientific verification. Video checks are not implemented.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('source', type=Path)
    init.add_argument('output', type=Path)
    init.add_argument('--format', choices=('reader-card', 'text'), required=True)
    init.add_argument('--article-type', choices=TYPES, default='unknown')
    init.add_argument('--coverage', choices=('full', 'abstract', 'partial', 'unknown'), default='unknown')
    init.add_argument('--language', default='zh-CN')
    init.add_argument('--seconds', type=float, default=None, help='Optional duration requested by user; omitted means content-led, no time budget.')
    check = sub.add_parser('validate')
    check.add_argument('project', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'init':
            project = create_project(args.source, args.format, args.article_type, args.coverage, args.language, args.seconds)
            result = validate(project)
            require(result['contract_valid'], str(result['errors']))
            write_new(args.output, project)
        else:
            result = validate(read_json(args.project))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['contract_valid'] else 1
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
