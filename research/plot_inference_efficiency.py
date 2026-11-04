"""Standalone scientific figures from validated cell metrics, using Matplotlib."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parents[1]
d=json.loads((ROOT/'docs/inference-efficiency-results.json').read_text())
plt.rcParams.update({'font.size':11,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
for metric,filename,xlabel in [('mean_output_tokens','tokens','Mean total output tokens per question'),('mean_request_seconds','runtime','Mean serial request time (seconds)')]:
 fig,axes=plt.subplots(1,2,figsize=(12,5.7),layout='constrained',sharey=True)
 for ax,service in zip(axes,['granite','deepseek']):
  cells=[c for c in d['cells'] if c['service']==service and c['complete_cell']]
  for mode in {c['mode'] for c in cells}:
   pair=sorted([c for c in cells if c['mode']==mode],key=lambda c:c['cap'])
   if len(pair)==2:ax.plot([c[metric] for c in pair],[c['accuracy_percent'] for c in pair],color='#999999',linewidth=.8,linestyle='--',zorder=1)
  for i,c in enumerate(cells):
   color='#287c48' if c['cap']==2048 else '#be6a23';marker={'nonthinking':'o','low':'s','thinking':'^','high':'^','max':'D'}[c['mode']]
   low,high=c['accuracy_wilson95_percent'];y=c['accuracy_percent'];x=c[metric]
   ax.errorbar(x,y,yerr=[[y-low],[high-y]],fmt=marker,color=color,capsize=3,markersize=8 if c['cap']==512 else 5.5,
    markerfacecolor='none' if c['cap']==512 else color,alpha=.85,zorder=2)
  if not cells:ax.text(.5,.5,'Awaiting completed cells',transform=ax.transAxes,ha='center',color='#777777')
  ax.set_title('Granite 4.2 3B · A100' if service=='granite' else 'DeepSeek V4 Pro · API')
  ax.set_xlabel(xlabel);ax.set_ylim(0,103);ax.set_yticks(range(0,101,20));ax.set_xlim(left=0);ax.grid(alpha=.18)
 axes[0].set_ylabel('Reference matches (%)')
 fig.suptitle('Same 32 development questions · one sample per mode and cap',fontsize=14)
 handles=[Line2D([0],[0],color='#be6a23',label='512-token cap (hollow)'),Line2D([0],[0],color='#287c48',label='2048-token cap (filled)')]
 handles += [Line2D([0],[0],marker=marker,color='#444444',linestyle='',label=label) for marker,label in [('o','Nonthinking'),('s','Low effort'),('^','Thinking / high'),('D','Max (DeepSeek)')]]
 fig.legend(handles=handles,loc='outside lower center',ncol=3,frameon=False)
 for ext in ['svg','png']:
  fig.savefig(ROOT/f'docs/figures/inference-efficiency-{filename}.{ext}',dpi=170,metadata={'Description':'Development diagnostic, not equal hardware. Error bars: Wilson 95% question intervals.'} if ext=='svg' else None)
 plt.close(fig)
print('Saved token and runtime SVG/PNG figures')
