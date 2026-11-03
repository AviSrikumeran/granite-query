"""Append-only, explicitly public research journal and static dashboard export."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

WORKSPACE = Path(__file__).resolve().parents[2]
JOURNAL = WORKSPACE / 'progress/events.jsonl'
SITE = WORKSPACE / 'docs'
KINDS = {'completed', 'in_progress', 'failed', 'resolved', 'planned', 'decision'}

def now():
    return datetime.now(timezone.utc).isoformat()

def clean(value):
    value = str(value).strip()
    if len(value) > 2500:
        raise ValueError('Public journal field exceeds 2500 characters')
    if re.search(r'(?i)(?:\b(?:sk-|ak-|as-)[a-z0-9_-]{10,}|bearer\s+\S+|(?:api_key|token_secret|password)\s*[:=]\s*\S+|[a-z]:\\users\\)', value):
        raise ValueError('Potential credential or private local path in public journal')
    return value

def read_events():
    return [json.loads(line) for line in JOURNAL.read_text(encoding='utf-8').splitlines() if line.strip()] if JOURNAL.exists() else []

def record(kind, title, detail, event_id=None):
    if kind not in KINDS:
        raise ValueError('Unsupported event kind')
    title, detail = clean(title), clean(detail)
    event_id = clean(event_id or hashlib.sha256((kind + title + detail).encode()).hexdigest()[:20])
    if any(e['id'] == event_id for e in read_events()):
        return False
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    event = {'id': event_id, 'at_utc': now(), 'kind': kind, 'title': title, 'detail': detail}
    with JOURNAL.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + '\n')
    return True

def build(status=None):
    events = read_events()
    status = status or {}
    pilot = status.get('teacher_pilot', {})
    current_path = JOURNAL.parent / 'current.json'
    current = json.loads(current_path.read_text(encoding='utf-8')) if current_path.exists() else {}
    # Explicit allowlist: never export raw logs, credentials, prompts, responses or account metadata.
    public = {'schema_version': 1, 'generated_at_utc': now(),
        'title': 'Granite Query', 'subtitle': 'Learning More from Less',
        'research_question': 'Can student aware data selection help Granite learn mathematical reasoning from DeepSeek more efficiently than random selection?',
        'stage': clean(current.get('stage', 'Awaiting recorded stage')),
        'next_action': clean(status.get('next_action', 'Implement and validate the Granite training smoke test.')),
        'metrics': {'teacher_responses': pilot.get('completed', 0),
            'strict_answer_passes': pilot.get('verified_final_answers', 0),
            'training_completed': bool(current.get('training_completed', False)),
            'held_out_evaluation_completed': bool(current.get('held_out_evaluation_completed', False))},
        'limits': {'modal_usd': 30, 'deepseek_usd': 20},
        'training_progress': {k: v for k, v in status.get('training_progress', {}).items()
                              if k in ('stage', 'steps', 'total_steps', 'elapsed_seconds', 'supervised_tokens')},
        'caveat': 'Teacher pilot uses training questions. It is not held-out accuracy or evidence of Granite improvement.',
        'events': events}
    audit_path=WORKSPACE/'docs/project-status.json'
    if audit_path.exists():
        audit=json.loads(audit_path.read_text(encoding='utf-8'))
        work=audit.get('current_work',[])
        active=next((r for r in work if r.get('status')=='running'),None) or next((r for r in work if r.get('status')=='queued'),None)
        if active:
            public['stage']=clean(active['title'])
            public['next_action']=clean(active['detail'])
    summary_path=WORKSPACE/'granite_query/cloud/runs/ranked_random_32_seed42_v1/public_summary.json'
    if summary_path.exists():
        summary=json.loads(summary_path.read_text(encoding='utf-8'))
        fields=('count','numeric_correct','strict_format_correct','truncated','latency_seconds_total','generated_tokens','supervised_tokens')
        public['comparison']={'count':summary['count'],
            'metrics':{name:{k:v for k,v in row.items() if k in fields and isinstance(v,(int,float))}
                       for name,row in summary['metrics'].items() if name in ('baseline','ranked','random')},
            'ranked_minus_random_correct':summary['ranked_minus_random_correct'],
            'limitations':[clean(x) for x in summary['limitations']],
            'official_test_used':False}
    SITE.mkdir(parents=True, exist_ok=True)
    for name, data in [('status.json', public), ('events.json', events)]:
        tmp = SITE / (name + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        tmp.replace(SITE / name)
    lines = ['# Granite Query research journal', '', public['research_question'], '',
        'This is a generated, append-only history. Corrections are new events, not edits to earlier evidence.', '',
        'Current stage: ' + public['stage'], '', 'Next: ' + public['next_action'], '',
        '> ' + public['caveat'], '']
    for event in events:
        lines += [f"## {event['at_utc']} | {event['kind']} | {event['title']}", '', event['detail'], '']
    (JOURNAL.parent / 'JOURNAL.md').write_text('\n'.join(lines), encoding='utf-8')
    (SITE / 'journal.md').write_text('\n'.join(lines), encoding='utf-8')
    return public

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kind', choices=sorted(KINDS))
    parser.add_argument('--title')
    parser.add_argument('--detail')
    args = parser.parse_args()
    if args.kind:
        if not args.title or not args.detail:
            parser.error('--kind requires --title and --detail')
        record(args.kind, args.title, args.detail)
    source = WORKSPACE / 'granite_query/cloud/runs/supervisor/status.json'
    result = build(json.loads(source.read_text(encoding='utf-8')) if source.exists() else None)
    print(json.dumps({'events': len(result['events']), 'exported': True}))

if __name__ == '__main__':
    main()
