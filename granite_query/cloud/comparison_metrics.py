"""Frozen numerical development scoring, with formatting/truncation separated."""
import re
from decimal import Decimal

NUMBER=re.compile(r'[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)')

def score(row):
    text=row['response'].strip()
    truncated=bool(row.get('truncated'))
    has_marker='####' in text
    final=text.rsplit('####',1)[1].strip() if has_marker else (text.splitlines()[-1] if text else '')
    numbers=NUMBER.findall(final)
    predicted=Decimal(numbers[-1].replace(',','')) if numbers else None
    gold=Decimal(str(row['gold_answer']).replace(',',''))
    # No attempt to infer correctness from an unfinished generation.
    correct=not truncated and predicted==gold
    strict=correct and has_marker and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',final.replace(',','')) is not None
    return {'correct':correct,'strict_format_correct':strict,'truncated':truncated,
        'prediction':str(predicted) if predicted is not None else None,
        'extraction':'marker' if has_marker else 'last_nonempty_line'}

def summarize(rows):
    scores=[score(r) for r in rows]
    return {'count':len(rows),'numeric_correct':sum(s['correct'] for s in scores),
        'strict_format_correct':sum(s['strict_format_correct'] for s in scores),
        'truncated':sum(s['truncated'] for s in scores),
        'latency_seconds_total':sum(r['elapsed_seconds'] for r in rows),
        'generated_tokens':sum(r['generated_tokens'] for r in rows),
        'scoring_policy':'Last number after ####, else last number on final nonempty line; truncated generations never counted correct. Heuristic numeric scoring, not reasoning-step verification.'}
