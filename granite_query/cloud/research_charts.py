"""Measured-only, matched-question research figures; no fabricated improvement points."""
import json
from pathlib import Path
import math
import os

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'runs/matplotlib_cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def wilson(correct,total):
    p=correct/total; z=1.96; d=1+z*z/total
    center=(p+z*z/(2*total))/d
    margin=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/d
    return 100*(center-margin),100*(center+margin)

def build():
    folder=WORKSPACE/'docs/figures'
    folder.mkdir(parents=True,exist_ok=True)
    teacher=json.loads((ROOT/'runs/matched_teacher16_v1/summary.json').read_text())
    original=json.loads((ROOT/'runs/ranked_random_32_seed42_v1/public_summary.json').read_text())
    teacher_ids=set(json.loads((ROOT/'runs/matched_teacher16_v1/manifest.json').read_text())['ids'])
    student_ids=set(json.loads((ROOT/'runs/ranked_random_32_seed42_v1/plan.json').read_text())['development_ids'])
    if teacher_ids!=student_ids:
        raise ValueError('Cannot plot unmatched teacher/student question sets')
    models=[('DeepSeek Pro\n(thinking API)',teacher),('Original\nGranite',original['metrics']['baseline']),
            ('Granite\nBM25 /32',original['metrics']['ranked']),('Granite\nrandom /32',original['metrics']['random'])]
    plt.rcParams.update({'svg.fonttype':'none','font.size':11,'axes.spines.top':False,'axes.spines.right':False,
        'figure.facecolor':'#101311','axes.facecolor':'#101311','text.color':'#e8ece6',
        'axes.labelcolor':'#e8ece6','xtick.color':'#e8ece6','ytick.color':'#a7b2a4','axes.edgecolor':'#536050'})
    def accuracy_chart(items,title,filename,note):
        fig,ax=plt.subplots(figsize=(10,5.6))
        values=[100*m['numeric_correct']/m['count'] for _,m in items]
        errors=[wilson(m['numeric_correct'],m['count']) for _,m in items]
        bars=ax.bar(range(len(items)),values,color=['#b7a7ed']+['#c5ed90']*(len(items)-1),width=.58)
        ax.errorbar(range(len(items)),values,
            yerr=[[v-low for v,(low,high) in zip(values,errors)],[high-v for v,(low,high) in zip(values,errors)]],
            fmt='none',ecolor='#eab788',capsize=5,linewidth=1.3)
        for bar,(_,m) in zip(bars,items):
            ax.text(bar.get_x()+bar.get_width()/2,4,f"{m['numeric_correct']}/{m['count']}\n{100*m['numeric_correct']/m['count']:.2f}%",ha='center',va='bottom',color='#101311',fontweight='bold')
        ax.set_xticks(range(len(items)),[name for name,_ in items])
        ax.set_ylim(0,105);ax.set_ylabel('Reference-answer accuracy (%)')
        ax.set_title(title,loc='left',pad=20,fontweight='bold');ax.yaxis.grid(True,alpha=.13);ax.set_axisbelow(True)
        fig.text(.1,.025,note,fontsize=9,color='#a7b2a4')
        fig.subplots_adjust(bottom=.22,top=.85,left=.1,right=.97)
        for extension in ('png','svg'):
            fig.savefig(folder/(filename+'.'+extension),dpi=180,facecolor=fig.get_facecolor())
        plt.close(fig)
    accuracy_chart(models,'DeepSeek and Granite on the same 16 questions','matched16-accuracy',
        'Development pilot, n=16. Lines:95% Wilson intervals. Thinking and token budgets differ. Not final-test results.')
    # Same-question learning history: only measured Granite checkpoints are drawn.
    fig,ax=plt.subplots(figsize=(10,5.2))
    baseline=100*original['metrics']['baseline']['numeric_correct']/16
    ax.plot([0,32],[baseline,100*original['metrics']['ranked']['numeric_correct']/16],'o-',color='#c5ed90',label='BM25 selected')
    ax.plot([0,32],[baseline,100*original['metrics']['random']['numeric_correct']/16],'s--',color='#79b8ce',label='Random selected')
    ax.axhline(100*teacher['numeric_correct']/16,color='#b7a7ed',linestyle=':',label='DeepSeek reference')
    ax.set(xlim=(-3,40),ylim=(0,100),xlabel='Teacher training examples',ylabel='Accuracy on the same16 questions (%)')
    ax.set_title('Measured progress so far: no accuracy gain in the first pilot',loc='left',pad=16)
    ax.legend(loc='lower right');ax.grid(alpha=.13)
    fig.text(.1,.025,'The new64-question evaluation is a separate series. Do not join scores across different question sets.',fontsize=9,color='#a7b2a4')
    fig.subplots_adjust(bottom=.2,left=.1,right=.97)
    for ext in ('png','svg'):
        fig.savefig(folder/('pilot-learning-history.'+ext),dpi=180,facecolor=fig.get_facecolor())
    plt.close(fig)
    public={'matched16':{'count':16,'teacher_correct':teacher['numeric_correct'],
        'granite_original_correct':original['metrics']['baseline']['numeric_correct'],
        'granite_ranked32_correct':original['metrics']['ranked']['numeric_correct'],
        'granite_random32_correct':original['metrics']['random']['numeric_correct'],
        'settings_note':'DeepSeek thinking/4096 output tokens; Granite non-thinking/512. API round-trip and GPU-generation timing differ.'},
        'matched64':{'stage':'in_progress'},'training120':{'stage':'queued'},
        'figures':['figures/matched16-accuracy.svg','figures/pilot-learning-history.svg']}
    evalpath=ROOT/'runs/matched_eval64_v1/metrics.json'
    trainfolder=ROOT/'runs/granite_full120_v1'
    if (trainfolder/'launch.json').exists():
        launch=json.loads((trainfolder/'launch.json').read_text())
        if launch.get('call_id'):
            statuspath=trainfolder/'remote_status.json'
            status=json.loads(statuspath.read_text()) if statuspath.exists() else {}
            public['training120']={'stage':status.get('stage','running')}
    teacher64path=ROOT/'runs/matched_eval64_v1/teacher/summary.json'
    recovered=ROOT/'runs/matched_eval64_v1/recovered_baseline64.json'
    if (evalpath.exists() or recovered.exists()) and teacher64path.exists():
        expected64=set(json.loads((ROOT/'runs/matched_eval64_v1/plan.json').read_text())['development_ids'])
        actual64=set(json.loads((ROOT/'runs/matched_eval64_v1/teacher/manifest.json').read_text())['ids'])
        if expected64!=actual64 or len(expected64)!=64:
            raise ValueError('Cannot combine unmatched64 evaluation sets')
        if evalpath.exists():
            metrics=json.loads(evalpath.read_text())
        else:
            from comparison_metrics import summarize
            rows=json.loads(recovered.read_text())
            if len(rows)!=64 or {r['id'] for r in rows}!=expected64:
                raise ValueError('Recovered baseline is not a complete matched64 phase')
            metrics={'baseline':summarize(rows)}
        t=json.loads(teacher64path.read_text())
        items=[('DeepSeek Pro',t)]+[(name,metrics[name]) for name in ('baseline','ranked32','random32') if name in metrics]
        fullpath=ROOT/'runs/granite_full120_v1/metrics.json'
        if fullpath.exists():
            full=json.loads(fullpath.read_text())['full120'];items.append(('Granite full120',full));public['training120']={'stage':'completed','correct':full['numeric_correct']}
        accuracy_chart(items,'Matched64-question development evaluation','matched64-accuracy',
            'Same64 monitoring questions. Lines:95% Wilson intervals. Development, not final-test accuracy.')
        public['matched64']={'stage':'completed' if evalpath.exists() else 'partial','count':64,'correct':{name:m['numeric_correct'] for name,m in items}}
        public['figures'].append('figures/matched64-accuracy.svg')
    (WORKSPACE/'progress/research_summary.json').write_text(json.dumps(public,indent=2),encoding='utf-8')
    (WORKSPACE/'docs/research.json').write_text(json.dumps(public,indent=2),encoding='utf-8')
    return public

if __name__=='__main__':
    print(json.dumps(build()))
