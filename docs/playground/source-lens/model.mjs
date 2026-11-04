// Original illustrative material. These are interface examples, not study results.
export const RECORD = Object.freeze({
  id: 'DEMO–001',
  title: 'A fair comparison',
  kind: 'Protocol note',
  question: 'What makes a comparison interpretable?',
  description: 'An authored example of how a research note can become linked, inspectable evidence.'
});

export const PASSAGES = Object.freeze([
  Object.freeze({
    id: 'cohort', line: '01', label: 'Freeze the cohort', key: 'cohort',
    title: 'The questions stay the same.',
    quote: 'Both variants use the same fixed set of evaluation questions. The cohort is frozen before either result is inspected.',
    value: 'Same questions for both variants',
    explanation: 'A shared question set keeps the comparison attached to the same evaluation scope.',
    boundary: 'This establishes scope. It does not establish a performance gain.'
  }),
  Object.freeze({
    id: 'exposure', line: '02', label: 'Match the exposure', key: 'exposure',
    title: 'The training budget is explicit.',
    quote: 'Training exposure is matched by supervised token count and optimizer updates. Example counts may differ.',
    value: 'Matched tokens and updates',
    explanation: 'The record states which parts of the training budget are matched, and which are allowed to differ.',
    boundary: 'Equal example counts alone would not demonstrate equal training exposure.'
  }),
  Object.freeze({
    id: 'changes', line: '03', label: 'Keep both directions', key: 'outcomes',
    title: 'Corrections and regressions both count.',
    quote: 'Question-level changes are recorded as corrections, regressions and unchanged outcomes. Aggregate accuracy is reported alongside them.',
    value: 'Corrections, regressions, unchanged',
    explanation: 'A total score is easier to interpret when the underlying changes remain visible.',
    boundary: 'A higher total alone does not explain why a variant changed.'
  }),
  Object.freeze({
    id: 'uncertainty', line: '04', label: 'Keep the qualification', key: 'uncertainty',
    title: 'The conclusion keeps its limits.',
    quote: 'Uncertainty and cohort limitations accompany the reported difference. An exploratory comparison is not presented as a general result.',
    value: 'Difference plus uncertainty and scope',
    explanation: 'The qualification travels with the finding instead of disappearing into a footnote.',
    boundary: 'This illustrative note contains no measured score or model result.'
  })
]);

export function passageIndex(value) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.min(PASSAGES.length - 1, Math.max(0, Math.round(n))) : 0;
}

export function evidenceFor(index) {
  const passage = PASSAGES[passageIndex(index)];
  return {
    record: RECORD.id,
    type: 'illustrative_evidence',
    field: passage.key,
    value: passage.value,
    source: { title: RECORD.title, line: passage.line, quote: passage.quote },
    limitation: passage.boundary
  };
}
