// Original explanatory pseudocode and diagram metadata. No execution takes place.
export const STEPS=Object.freeze([
  {id:'scope',number:'01',label:'Define the scope',short:'Shared cohort',lines:'02–06',statement:'One question set anchors the comparison.',explanation:'The scope record identifies which questions belong to the comparison. Both variants connect to the same cohort.',artifact:'Cohort record',boundary:'Selecting this region explains the scope; it does not load questions or execute evaluation.'},
  {id:'budget',number:'02',label:'State the exposure',short:'Exposure budget',lines:'08–12',statement:'Make the matching rule explicit.',explanation:'The budget record states supervised token and update limits. Example count and elapsed time remain separate quantities.',artifact:'Budget record',boundary:'The bars are conceptual matching marks. They do not display measured training amounts.'},
  {id:'compare',number:'03',label:'Pair the outcomes',short:'Paired comparison',lines:'14–18',statement:'Match each outcome to its question.',explanation:'The two variants meet at a question-level comparison. Corrections, regressions and unchanged outcomes would all remain visible.',artifact:'Comparison record',boundary:'The paired rows represent a relationship, not actual questions, answers or accuracy scores.'},
  {id:'qualify',number:'04',label:'Keep the limits',short:'Qualified report',lines:'20–25',statement:'A finding carries its interval and scope.',explanation:'The report keeps the difference, uncertainty and cohort scope together. The diagram explains the protocol without inventing a result.',artifact:'Qualified report',boundary:'This illustrative report makes no measured performance or generalization claim.'}
].map(Object.freeze));
export const LAYOUTS=Object.freeze({
  wide:{viewBox:'0 0 800 550',positions:{scope:[20,50],budget:[20,320],compare:[300,190],qualify:[580,170]},paths:{scope:'M220 130H260V250H300',budget:'M220 400H260V300H300',qualify:'M500 270H580'}},
  narrow:{viewBox:'0 0 390 930',positions:{scope:[95,40],budget:[95,260],compare:[95,480],qualify:[95,700]},paths:{scope:'M195 200H55V560H95',budget:'M195 420V480',qualify:'M195 640V700'}}
});
export const indexOfStep=id=>Math.max(0,STEPS.findIndex(step=>step.id===id));
export const nextStep=index=>Math.min(STEPS.length-1,Math.max(0,Number.isFinite(index)?Math.trunc(index)+1:0));
