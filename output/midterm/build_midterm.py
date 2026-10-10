import zipfile,xml.etree.ElementTree as E,json
from pathlib import Path
D=Path(__file__).parent
P='http://schemas.openxmlformats.org/presentationml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
K='http://schemas.openxmlformats.org/package/2006/relationships'
C='http://schemas.openxmlformats.org/package/2006/content-types'
ns={'p':P,'a':A}
for k,v in [('p',P),('a',A),('r',R)]: E.register_namespace(k,v)
z=zipfile.ZipFile('/var/folders/4l/gtzq7qts5ns9m0vtn00zfz6m0000gn/T/browser-use/exports/Powerpoint_UbiComp_2023_Template (1)-0c7840e2-f9c3-44f8-a6d4-0827155d6e92.pptx')
f={n:z.read(n) for n in z.namelist()}
S=[
['Privacy-aware\nrobot reminders','Watch-mediated consent\nMaster’s thesis midterm',['Aroosa Batool'],.5,'My thesis explores how a social robot can deliver a useful reminder without revealing private information to people nearby. I use an Ohbot, a Bangle.js watch and local sensing. Today I will show the prototype, component measurements and the study I am preparing.','README.md'],
['The privacy problem','A reminder changes meaning when someone else can hear it',['“Your doctor’s appointment is at 3 PM.”','Helpful when alone. Potentially revealing with a visitor.','The robot needs to choose public or private delivery.','The wearer makes the disclosure decision on the watch.'],1.5,'Use the appointment example throughout. Detection alone cannot determine whether sharing is socially acceptable. The watch lets the wearer respond discreetly and receive the reminder privately. Do not claim perfect privacy or visitor consent to recognition. Transition to the research questions.','README.md; docs/design_hld.md'],
['Research questions','Proposed questions for the current thesis scope',['RQ1: How can a robot coordinate sensing and private consent?','RQ2: How acceptable are microphone, camera and fallback packages?','RQ3: When do users prefer memory or fresh consent?'],1.25,'RQ1 addresses the architecture. RQ2 is the main empirical question in the revised story survey. RQ3 currently addresses stated preferences, since the main study does not manipulate memory. These are proposed questions, not completed findings. Contribution at midterm: an end-to-end prototype and a clearly scoped evaluation design.','README.md; user-study/story-survey-v2/research-design.md'],
['System components','Ohbot and Bangle.js communicate through a Python host',['Ohbot: spoken reminder or neutral greeting over USB.','Bangle.js: private Yes/No prompt and reminder over BLE.','Python: scheduling, sensitivity, recognition and policy.','Camera and microphone: estimate bystander presence.'],2.25,'The laptop coordinates reminder scheduling, sensitivity classification and presence sensing. It sends a consent request to the watch and commands the robot. BLE connectivity is a coarse owner-presence proxy, not proof of wearing or room location. Core presence processing is local. The watch provides both consent input and private delivery.','README.md; docs/technical_hld.md'],
['Reminder delivery policy','Sensitivity and social context determine the delivery path',['Non-sensitive: speak at the scheduled time.','Sensitive, no detected bystander: allow spoken delivery.','Bystander detected: request or retrieve a watch decision.','Yes: speak. No or no reply: deliver privately to the watch.'],2.25,'Walk through the four cases. Unanswered prompts never become remembered preferences. A refusal produces a neutral greeting and a watch note. The unified app withholds sensitive speech when sensing is inconclusive. Legacy fusion paths differ, so scope this safety behavior to the unified app. Recognition and sensitivity errors remain risks.','README.md; user-study/story-survey-v2/research-design.md'],
['Sensing packages','Coverage and sensing burden differ across packages',['Microphone: detects visitors who speak while listening.','Camera: detects visible faces, including silent visitors.','Fallback: microphone first, camera after an audio miss.','Face and voice identities remain separate.'],1.5,'A silent visitor can evade microphone detection. A camera has a limited field of view. Fusion escalates after no non-owner voice is detected, including the owner-alone case. It does not guarantee less sensing in every situation. Current packages also differ in activation duration and head movement, so the study estimates perceptions of complete packages.','README.md; user-study/story-survey-v2/research-design.md'],
['Consent memory','Remembered choices reduce prompts but may become stale',['Remember: reuse a recognized bystander’s explicit Yes/No.','Re-ask: request a fresh decision each time.','Both policies retain recognition galleries.','Expiry, topic-specific consent and watch editing are proposed.'],1.25,'Memory exists in camera, microphone and fusion apps. Re-ask stores no disclosure decisions but still retains recognition galleries. Apps use a broad reminder key, so an answer can transfer across topics. Current revocation requires clearing local state. The trade-off is convenience versus outdated preferences. Revised survey memory items measure preference, not a causal treatment effect.','README.md; user-study/story-survey-v2/research-design.md'],
['Prototype progress','The repository contains the full delivery workflow',['Implemented: reminder capture, scheduling and sensitivity.','Implemented: enrollment, sensing and watch consent.','Implemented: standalone and fused engines with both policies.','Prepared: presentation UI, benchmarks and survey materials.'],1.25,'This is the progress checkpoint. The repository contains integrated delivery paths, a local presentation workstation, evaluation capture tools and revised survey preparation materials. Code availability does not prove real-world recognition accuracy, trust or confirmed private receipt. No participant findings are claimed today. The next slide contains actual bundled component measurements.','README.md; robot/bench/results'],
['Early technical measurements','Bundled CPU measurements support further testing',['YuNet detection: 5.15 ms median per 640×480 frame.','SFace recognition: 7.33 ms per 112×112 face crop.','Resemblyzer: 23.74 ms per 6-second utterance.','Accuracy and end-to-end delay remain to measure.'],1.5,'Explain input sizes and units. Component latency is not total response time and excludes acquisition windows and user interaction. Do not rank face and voice models by these unlike units. Bundled ArcFace is 81.01 ms per crop and ECAPA is 31.28 ms per six-second utterance. Faster computation does not prove better identification. Labeled capture and false-match evaluation remain necessary.','robot/bench/results/camera_results.md; robot/bench/results/voice_results.md'],
['Main study design','Six matched stories compare three sensing packages',['Each person sees 2 microphone, 2 camera and 2 fallback stories.','Three topics crossed with friend/home and colleague/office.','Each package has one Yes/aloud and one No/private outcome.','Allocation and story order rotate across 36 cells.'],1.75,'The revised design is dated October 4. Six stories cross health, financial and personal topics with two relationship/settings. Each participant sees a story once, while sensing versions rotate between participants. Three allocations, two response schedules and six balanced orders yield 36 cells. This is not the sample size. Main visitors are detected in every package, enabling matched outcomes.','user-study/story-survey-v2/README.md; research-design.md'],
['Outcomes and analysis','Acceptability is the primary outcome',['Primary: Q10 acceptability, fallback versus each single sensor.','Secondary: privacy, trust, sensing comfort and control.','Planned: ordinal mixed model for repeated participant ratings.','Power simulation and a cognitive pilot precede recruitment.'],1.5,'Plan two primary contrasts with Holm correction. Account for participant dependence, base story, response schedule, actual outcome and presentation position. Core questions are adaptations or new items, not a validated scale. Optional RoSAS or MDMT modules would add burden. Participant N is the sampling unit. Sample size and survey duration require simulation and pilot evidence.','user-study/story-survey-v2/research-design.md'],
['Study interpretation','The main outcome concerns described sensing packages',['Main visitors speak, so the fallback camera stays inactive.','Timing and head movement differ between packages.','The no-sensor story changes policy and is exploratory.','Memory questions measure preference, not treatment effects.'],1.25,'Primary fallback stories do not test experiencing camera activation. Camera-only has a continuous session preview. Microphone has a scheduled five-minute window. The audit finds that fusion camera capture may fill the remaining interval, so do not describe every scan as brief. The no-sensor story is private-only and appears last. Hypothetical judgments cannot establish live behavior or visitor experience.','user-study/story-survey-v2/research-design.md'],
['Remaining work','Proposed sequence for the second half of the thesis',['1. Freeze behavior, stimuli and approved study information.','2. Pilot comprehension and burden, then finalize power.','3. Recruit, collect ratings and test recognition robustness.','4. Analyze effects and limitations, then complete the thesis.'],1.5,'Present a sequence rather than invented dates. Complete institutional, ethics, storage, retention and withdrawal details. Pilot active-sensor and consent comprehension. Technical tests need labeled data, silent visitors, off-camera visitors, false matches and failure paths. Freeze the analysis before collection. Ask whether the current package comparison is sufficient or a distinct live fallback evaluation should be prioritized.','user-study/story-survey-v2/README.md; docs/algorithm_comparison.md'],
['Midterm takeaway','The prototype is implemented. Human evaluation is next.',['The watch provides private consent and delivery.','Early latency measurements support component feasibility.','The revised study separates sensing from memory preferences.','Feedback: retain this scope or add live fallback evaluation?'],.75,'Close: the system implements a concrete privacy-aware reminder workflow. Early measurements address feasibility. The next phase addresses acceptability and recognition robustness. Request feedback on the package-comparison scope and whether a separate live fallback test is needed. Pause for questions.','README.md; user-study/story-survey-v2/research-design.md'],
['Discussion','Thank you',['Study scope and fallback evaluation','Consent expiry and changing social context','Recognition robustness and sensing permissions'],0,'Outside the 20-minute speaking budget. Likely answers: BLE does not prove room presence. Re-ask does not delete recognition galleries. Consent expiry is proposed. The survey does not establish live behavior. Silent visitors can evade microphone detection and trigger camera fallback. No participant results are available in these materials.','user-study/story-survey-v2/research-design.md']
]
print("Total",sum(x[3] for x in S))
def parse(b): return E.fromstring(b)
def serialize(e): return E.tostring(e,encoding='utf-8',xml_declaration=True)
def write_text(sh,lines,size,color,bold=False,gap=1200):
 tx=sh.find('p:txBody',ns)
 if tx is None:return
 for p in tx.findall('a:p',ns):tx.remove(p)
 if isinstance(lines,str):lines=lines.split('\n')
 for line in lines:
  p=E.SubElement(tx,'{'+A+'}p'); pp=E.SubElement(p,'{'+A+'}pPr',{'marL':'0','indent':'0'})
  E.SubElement(pp,'{'+A+'}buNone')
  E.SubElement(E.SubElement(pp,'{'+A+'}spcAft'),'{'+A+'}spcPts',{'val':str(gap)})
  E.SubElement(E.SubElement(pp,'{'+A+'}lnSpc'),'{'+A+'}spcPct',{'val':'110000'})
  r=E.SubElement(p,'{'+A+'}r'); rp=E.SubElement(r,'{'+A+'}rPr',{'sz':str(size),'b':'1' if bold else '0'})
  E.SubElement(rp,'{'+A+'}latin',{'typeface':'Calibri'})
  E.SubElement(E.SubElement(rp,'{'+A+'}solidFill'),'{'+A+'}srgbClr',{'val':color})
  E.SubElement(r,'{'+A+'}t').text=line
ct=parse(f['[Content_Types].xml']); pres=parse(f['ppt/presentation.xml']); ids=pres.find('p:sldIdLst',ns); ids.clear()
pr=parse(f['ppt/_rels/presentation.xml.rels'])
for r in list(pr):
 if r.get('Type')==R+'/slide':pr.remove(r)
notes_md=['# 20-minute midterm rehearsal sheet','Rehearse slides 1, 5, 10, 12 and 14 first. Then read the remaining cues.','']
for i,s in enumerate(S,1):
 root=parse(z.read('ppt/slides/slide1.xml' if i==1 else 'ppt/slides/slide3.xml')); tree=root.find('p:cSld/p:spTree',ns)
 for sh in list(tree):
  if sh.tag!='{'+P+'}sp':continue
  ph=sh.find('p:nvSpPr/p:nvPr/p:ph',ns)
  if ph is None:continue
  typ=ph.get('type'); idx=ph.get('idx')
  if i==1:
   if typ=='pic':tree.remove(sh)
   elif typ=='ctrTitle':
    write_text(sh,s[0],3200,'FFFFFF',True,0)
    x=sh.find('p:spPr/a:xfrm',ns);x.find('a:off',ns).set('y','2350000');x.find('a:ext',ns).set('cy','1800000')
   elif typ=='subTitle':
    write_text(sh,s[1],1800,'FFFFFF',gap=500)
    x=sh.find('p:spPr/a:xfrm',ns);x.find('a:off',ns).set('y','4200000');x.find('a:ext',ns).set('cy','1000000')
   elif typ=='body':write_text(sh,s[2],1400,'FFFFFF',gap=0)
  else:
   if typ=='title':write_text(sh,s[0],3200,'173E56',True,0)
   elif typ=='body' and idx=='1':write_text(sh,s[2],2400,'FFFFFF',gap=1400)
   elif typ=='body' and idx=='2':write_text(sh,s[1],2000,'173E56',gap=0)
  if typ=='dt':write_text(sh,'5 October 2026',800,'FFFFFF' if i==1 else '666666',gap=0)
  if typ=='ftr':write_text(sh,'Master’s thesis midterm',800,'666666',gap=0)
  if typ=='sldNum':write_text(sh,str(i),800,'666666',gap=0)
 f[f'ppt/slides/slide{i}.xml']=serialize(root)
 rel=E.Element('{'+K+'}Relationships')
 for rid,typ,tgt in [('rId1','slideLayout',f'../slideLayouts/slideLayout{1 if i==1 else 3}.xml'),('rId2','notesSlide',f'../notesSlides/notesSlide{i}.xml')]:E.SubElement(rel,'{'+K+'}Relationship',{'Id':rid,'Type':R+'/'+typ,'Target':tgt})
 f[f'ppt/slides/_rels/slide{i}.xml.rels']=serialize(rel)
 notes=parse(z.read('ppt/notesSlides/notesSlide3.xml'))
 cue=f'TARGET: {s[3]:g} minutes. CUMULATIVE: {sum(t[3] for t in S[:i]):g} minutes.\n\n{s[4]}\n\nSource: {s[5]}'
 write_text(notes.findall('.//p:sp',ns)[0],cue,1200,'000000',gap=300)
 f[f'ppt/notesSlides/notesSlide{i}.xml']=serialize(notes)
 nr=E.Element('{'+K+'}Relationships')
 for rid,typ,tgt in [('rId1','notesMaster','../notesMasters/notesMaster1.xml'),('rId2','slide',f'../slides/slide{i}.xml')]:E.SubElement(nr,'{'+K+'}Relationship',{'Id':rid,'Type':R+'/'+typ,'Target':tgt})
 f[f'ppt/notesSlides/_rels/notesSlide{i}.xml.rels']=serialize(nr)
 rid=f'rIdMidterm{i}'
 E.SubElement(ids,'{'+P+'}sldId',{'id':str(255+i),'{'+R+'}id':rid})
 E.SubElement(pr,'{'+K+'}Relationship',{'Id':rid,'Type':R+'/slide','Target':f'slides/slide{i}.xml'})
 for part,content in [(f'/ppt/slides/slide{i}.xml','application/vnd.openxmlformats-officedocument.presentationml.slide+xml'),(f'/ppt/notesSlides/notesSlide{i}.xml','application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml')]:
  if not any(e.get('PartName')==part for e in ct):E.SubElement(ct,'{'+C+'}Override',{'PartName':part,'ContentType':content})
 notes_md += [f'## {i}. '+s[0].replace('\n',' ')+f' ({s[3]:g} min)',s[4],'']
f['ppt/presentation.xml']=serialize(pres);f['ppt/_rels/presentation.xml.rels']=serialize(pr);f['[Content_Types].xml']=serialize(ct)
with zipfile.ZipFile(D/'Midterm-Presentation.pptx','w',zipfile.ZIP_DEFLATED) as dst:
 for n,b in f.items():dst.writestr(n,b)
(D/'Presenter-Notes.md').write_text('\n'.join(notes_md))
(D/'slides.json').write_text(json.dumps(S,indent=2))
print('15 slides created. 20-minute speaking schedule.')
