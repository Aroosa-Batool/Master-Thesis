const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(__dirname + '/survey.js', 'utf8');
function load(materials = false) {
 const nodes = new Map();
 function node(id) {
  if (!nodes.has(id)) nodes.set(id, {innerHTML:'', fields:[], hidden:false, addEventListener(t,f){this[t]=f;}, focus(){}, querySelectorAll(){return this.fields;}});
  return nodes.get(id);
 }
 const window = {location:{search:'?preview=1&cell=L1-A-W1'},SURVEY_MATERIALS_MODE:materials, addEventListener(){},scrollTo(){}};
 const document = {getElementById:node,querySelector:node,body:{classList:{add(){}}}};
 vm.runInNewContext(source,{window,document,URLSearchParams,Uint32Array,console,setTimeout,clearTimeout});
 return {window,nodes,node};
}
(async()=>{
 const app=load(), assign=app.window.SURVEY_DESIGN.assignment;
 for(let l=1;l<=3;l++) for(const a of ['A','B']) for(let w=1;w<=6;w++) {
  const cell=`L${l}-${a}-W${w}`, x=assign(cell); assert.equal(x.cell_id,cell);
  assert.equal(new Set(x.stories.map(s=>s.story_id)).size,6);
  for(const mode of ['M','C','F']) {
   const group=x.stories.filter(s=>s.condition===mode);
   assert.equal(group.length,2); assert.equal(new Set(group.map(s=>s.relationship)).size,2);
   assert.equal(new Set(group.map(s=>s.watch_response)).size,2);
  }
 }
 app.node('page').fields=[{name:'C1',type:'radio',value:'agree',checked:true}];
 await app.node('survey').submit({preventDefault(){}});
 assert(app.node('page').innerHTML.includes('Meet the robot'));
 app.node('page').fields=[];
 for(let i=0;i<10;i++) await app.node('survey').submit({preventDefault(){}});
 assert(app.node('page').innerHTML.includes('Review and finish'));
 await app.node('survey').submit({preventDefault(){}});
 assert(app.node('page').innerHTML.includes('Download'));
 const material=load(true).node('page').innerHTML;
 assert.equal((material.match(/Story [1-6] of 6/g)||[]).length,6);
 assert(material.includes('A private-only approach')); assert(material.includes('Your overall preferences'));
 assert(!material.includes('Not yet supplied')); assert(!material.includes('during the camera check'));
 const template=fs.readFileSync(__dirname+'/index.html','utf8');
 const staticHtml=template.replace(/  <script[^>]*><\/script>\n/g,'').replace('<body>','<body class="materials">').replace('<section id="page" tabindex="-1" aria-labelledby="page-title"></section>', '<section id="page">'+material+'</section>').replace(/<div class="progress-row">.*?<\/div>/,'').replace(/<progress.*?<\/progress>/,'').replace(/<nav id="navigation"[\s\S]*?<\/nav>/,'').replace(/<noscript>[\s\S]*?<\/noscript>/,'');
 fs.writeFileSync(__dirname+'/questionnaire.html',staticHtml);
 console.log('PASS: 36 assignment cells, complete optional-answer flow, local finish, seven story questionnaires, standalone questionnaire.');
})().catch(e=>{console.error(e);process.exit(1)});
