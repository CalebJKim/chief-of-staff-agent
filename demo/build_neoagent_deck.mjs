import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {ARTIFACT_MODULE,PRESENTATIONS_SKILL:skill,RUNTIME_PYTHON,BUILD_DIR,REPO_ROOT}=process.env;
const {Presentation,PresentationFile}=await import(pathToFileURL(ARTIFACT_MODULE).href);
const {resolvePresentationFont,finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const family=resolvePresentationFont();
const content=JSON.parse(await fs.readFile(path.join(REPO_ROOT,'demo/neoagent_deck.json'),'utf8'));
const p=Presentation.create({slideSize:{width:1280,height:720}});
const green='#9DD67C',white='#F2F5EF',muted='#B9C5BA',background='#16201B';
function text(s,value,x,y,w,h,size,color,bold=false){
 const t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 t.text=value;t.text.style={typeface:family,fontSize:size,bold,color,autoFit:'none'};return t;
}
for(const [i,item] of content.entries()){
 const s=p.slides.add();s.background.fill=background;
 // Title and body remain the first two text shapes for the existing reset/edit helpers.
 text(s,item.title,64,67,1152,95,i===0?56:42,white,true);
 text(s,item.body,66,185,1128,446,i===0?31:25,white);
 text(s,'NEOAGENT V2 / EXECUTIVE REVIEW',66,653,1030,28,16,green,true);
 text(s,String(i+1).padStart(2,'0'),1160,650,60,30,18,muted);
 text(s,i===0?'LEADERSHIP WORKING SESSION':'CAMPAIGN PLAN / DECISION-READY WORKING DECK',66,30,1110,26,14,green,true);
 s.speakerNotes.textFrame.setText(item.note);
}
await fs.mkdir(BUILD_DIR,{recursive:true});
const candidatePath=path.join(BUILD_DIR,'candidate.pptx');
await(await PresentationFile.exportPptx(p)).save(candidatePath);
const finalPath=path.join(BUILD_DIR,'final/neoagent-v2-exec-review.pptx');
await fs.mkdir(path.dirname(finalPath),{recursive:true});
await finalizePresentation({workspaceDir:BUILD_DIR,candidatePath,finalPath,pythonExecutable:RUNTIME_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
 explicitTotalSlideCount:10,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
 fontPolicy:{basis:'design',families:[family]},verifyArtifactToolImport:true,receiptPath:path.join(BUILD_DIR,'validation.json')});
for(const [i,s] of p.slides.items.entries()){
 const png=await p.export({slide:s,format:'png',scale:1});
 await fs.writeFile(path.join(BUILD_DIR,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
console.log(finalPath);
