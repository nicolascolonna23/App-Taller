const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('tema.js','utf8');
for (const light of [true,false]) {
 const sheets = {};
 const document = {documentElement:{dataset:{},style:{setProperty(){},removeProperty(){}}},head:{appendChild(node){sheets[node.id]=node}},getElementById:id=>sheets[id],createElement:()=>({}),querySelectorAll:()=>[]};
 const sandbox = {document,window:{},localStorage:{getItem:()=>null,setItem(){}},matchMedia:()=>({matches:light,addEventListener(){}}),fetch:()=>Promise.resolve({ok:false})};
 vm.runInNewContext(source,sandbox);
 for(const [palette,color] of Object.entries({diemar:'#6caeff',azul:'#3d8bfd',verde:'#22a06b',violeta:'#8b7bf7',rojo:'#e5484d',grafito:'#8a94a0'})){
  for(const theme of ['oscuro','claro','auto']){
   sandbox.window.Tema.poner({tema:theme,paleta:palette});
   assert(sheets['tema-css'].textContent.includes(`--brand:${color}!important;`));
   assert.equal(document.documentElement.dataset.modo,theme==='auto'?(light?'claro':'oscuro'):theme);
   assert(sheets['tema-css'].textContent.includes('--marca-ink:'));
  }
 }
}
console.log('PASS: six palettes, explicit themes, system theme and CSS precedence');
