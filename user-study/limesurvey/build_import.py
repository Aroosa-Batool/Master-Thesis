from pathlib import Path
from html.parser import HTMLParser
import csv, re, html, zipfile, json
ROOT=Path(__file__).resolve().parents[1]
class Node:
 def __init__(self,tag='',attrs=(),parent=None): self.tag=tag;self.attrs=dict(attrs);self.children=[];self.parent=parent
 def text(self): return ''.join(c.text() if isinstance(c,Node) else c for c in self.children)
 def find(self,tag):
  out=[]
  for c in self.children:
   if isinstance(c,Node):
    if c.tag==tag:out.append(c)
    out.extend(c.find(tag))
  return out
 def markup(self):
  if self.tag=='img': return '<p><img style="max-width:100%;height:auto" src="/upload/surveys/789223/images/'+self.attrs['asset']+'" alt="Alex wears a watch; Ohbot turns toward Sam, the bystander." /></p>'
  attrs=''.join(' '+k+'="'+html.escape(v,quote=True)+'"' for k,v in self.attrs.items() if k not in ['id','class'])
  content=''.join(c.markup() if isinstance(c,Node) else html.escape(c) for c in self.children)
  return '<'+self.tag+attrs+'>'+content+'</'+self.tag+'>'
class Parser(HTMLParser):
 def __init__(self):super().__init__();self.root=Node('root');self.current=self.root
 def handle_starttag(self,t,a):
  n=Node(t,a,self.current);self.current.children.append(n)
  if t not in ['img','input','meta','link','br']:self.current=n
 def handle_endtag(self,t):
  cur=self.current
  while cur.parent:
   if cur.tag==t:self.current=cur.parent;return
   cur=cur.parent
 def handle_data(self,d): self.current.children.append(d)
p=Parser();p.feed((ROOT/'participant-survey/questionnaire.html').read_text())
sections=[n for n in p.root.find('section') if n.attrs.get('class')=='material-section']
assert len(sections)==11
reader=csv.DictReader(Path('/Users/aroosabatool/Downloads/limesurvey_survey_789223.txt').open(encoding='utf-8-sig'),delimiter='\t'); headers=reader.fieldnames;template=list(reader)
rows=[r for r in template if r['class'] in ['S','SL']]
settings={'active':'N','format':'G','anonymized':'Y','ipaddr':'N','refurl':'N','allowsave':'N','allowprev':'Y','savetimings':'N','publicstatistics':'N','publicgraphs':'N','listpublic':'N','showprogress':'Y','showgroupinfo':'B','showqnumcode':'X','shownoanswer':'Y'}
for r in rows:
 if r['class']=='S' and r['name'] in settings:r['text']=settings[r['name']]
 if r['class']=='SL':
  if r['name']=='surveyls_title':r['text']='How should a reminder robot sense who is nearby? — Illustrated draft'
  if r['name']=='surveyls_description':r['text']='<p>A story-based study about privacy, comfort and control with Ohbot and a Bangle.js smartwatch.</p>'
  if r['name']=='surveyls_welcometext':r['text']='<p>Please complete the participant information and consent supplied separately by the researcher before answering. The stories are fictional and the illustrations are AI-generated. This survey does not activate your camera or microphone. All opinion and demographic questions are optional.</p>'
  if r['name']=='surveyls_endtext':r['text']='<p>Thank you for considering these situations. Your answers express opinions about a research prototype and proposed features.</p>'
qid=0;manifest=[]
def add(**kw):
 r=dict.fromkeys(headers,'');r.update(kw);rows.append(r);return r
for index,section in enumerate(sections):
 title=section.find('h1')[0].text()
 desc=[]
 for c in section.children:
  if not isinstance(c,Node):continue
  if c.tag=='fieldset' or c.tag=='label' or c.tag=='select' or c.tag=='textarea':break
  if c.tag=='h1':continue
  for im in ([c] if c.tag=='img' else c.find('img')):
   # home for intro, friend scenes S1/S3/S5 and S7; office for S2/S4/S6.
   home=index in [0,1,4,5,7]
   im.attrs['asset']=('home' if home else 'office')+'-triptych-neutral-v2.png'
  desc.append(c.markup())
 if index in [8,9]:desc=[] # explanation blocks inserted in exact order below
 add(id=str(index+1),**{'class':'G','type/scale':str(index+1),'name':('Story '+str(index)+' of 6 — ' if 1<=index<=6 else '')+title,'relevance':'1','text':''.join(desc),'language':'en'})
 # Sequential fields, with explanatory blocks between preference questions.
 children=section.children
 for c in children:
  if not isinstance(c,Node):continue
  if c.tag=='fieldset':
   qid+=1;legend=c.find('legend')[0].text(); inputs=c.find('input'); name=inputs[0].attrs['name'].replace('_','')
   assert all(i.attrs['name'].replace('_','')==name for i in inputs)
   typ='M' if inputs[0].attrs.get('type')=='checkbox' else 'L'
   add(id=str(qid),**{'class':'Q','type/scale':typ,'name':name,'relevance':'1','text':html.escape(legend),'language':'en','mandatory':'N','other':'N','encrypted':'N','same_default':'0','maximum_chars':'1500' if typ=='T' else ''})
   values=[]
   for label in c.find('label'):
    field=label.find('input')[0];code=field.attrs['value'];labeltext=re.sub(r'^([1-7])(?=[A-Za-z])',r'\1 ', ' '.join(label.text().split()));portalcode=('A'+str(len(values)+1)) if typ=='M' else (code if code in ['1','2','3','4','5','6','7','NA'] else str(len(values)+1));values.append({'code':code,'portal_code':portalcode,'label':labeltext})
    if typ=='M':
     qid+=1;add(id=str(qid),**{'class':'SQ','type/scale':'0','name':'A'+str(len(values)),'relevance':'1','text':html.escape(labeltext),'language':'en'})
    else:add(id=str(qid),**{'class':'A','type/scale':'0','name':str(len(values)) if code not in ['1','2','3','4','5','6','7','NA'] else code,'text':html.escape(labeltext),'language':'en'})
   manifest.append({'name':name,'type':typ,'wording':legend,'options':values})
  elif c.tag=='select':
   qid+=1;name=c.attrs['name'].replace('_','');label=next(n for n in section.find('label') if n.attrs.get('for')==c.attrs['id']).text()
   add(id=str(qid),**{'class':'Q','type/scale':'!','name':name,'relevance':'1','text':html.escape(label),'language':'en','mandatory':'N','other':'N','encrypted':'N'})
   for i,opt in enumerate(c.find('option')[1:],1):add(id=str(qid),**{'class':'A','type/scale':'0','name':str(i),'text':html.escape(opt.text()),'language':'en'})
   manifest.append({'name':name,'type':'!','wording':label})
  elif c.tag=='textarea':
   qid+=1;name=c.attrs['name'].replace('_','');label=next(n for n in section.find('label') if n.attrs.get('for')==c.attrs['id']).text()
   add(id=str(qid),**{'class':'Q','type/scale':'T','name':name,'relevance':'1','text':html.escape(label),'help':'Optional. Please avoid names and sensitive personal details.','language':'en','mandatory':'N','encrypted':'N','maximum_chars':'1500'})
   manifest.append({'name':name,'type':'T','wording':label})
  elif index in [8,9] and c.tag in ['p','h2']:
   qid+=1;add(id=str(qid),**{'class':'Q','type/scale':'X','name':'INFO'+str(qid),'relevance':'1','text':c.markup(),'language':'en','mandatory':'N'})
qid+=1
add(id=str(qid),**{'class':'Q','type/scale':'X','name':'CLOSING','relevance':'1','text':'<p>The stories are fictional and the pictures are AI-generated. Your answers express opinions about the described research prototype and proposed features.</p>','language':'en','mandatory':'N'})
# Imported answers follow original source order. Fixed assignment matches booklet L1-A-W1.
assert len({r['name'] for r in rows if r['class']=='Q'})==len([r for r in rows if r['class']=='Q'])
assert len([r for r in rows if r['class']=='Q' and r['name'].startswith('S') and re.search('Q(?:[1-9]|1[0-6])$',r['name'])])==112
out=ROOT/'limesurvey/university-survey.txt'
with out.open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,headers,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)
(ROOT/'limesurvey/question-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
with zipfile.ZipFile(ROOT/'limesurvey/story-images.zip','w',zipfile.ZIP_DEFLATED) as z:
 for scene in ['home','office']:
  f=ROOT/'participant-survey/assets'/f'{scene}-triptych-neutral-v2.png';z.write(f,'images/'+f.name)
print('Prepared',len([r for r in rows if r['class']=='Q']),'questions and',len(sections),'groups; file',out)
