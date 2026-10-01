// Build with the bundled artifact runtime. Supply ARTIFACT_MODULE, PRESENTATIONS_SKILL,
// RUNTIME_PYTHON and BUILD_DIR as absolute paths. Output is validated before copying.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const {ARTIFACT_MODULE, PRESENTATIONS_SKILL: skill, RUNTIME_PYTHON, BUILD_DIR} = process.env;
for (const value of [ARTIFACT_MODULE, skill, RUNTIME_PYTHON, BUILD_DIR]) {
  if (!path.isAbsolute(value ?? '')) throw new Error('Supply all four absolute runtime/build paths');
}
const {Presentation, PresentationFile} = await import(pathToFileURL(ARTIFACT_MODULE).href);
const {resolvePresentationFont, finalizePresentation} = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')).href);
const family = resolvePresentationFont();
const p = Presentation.create({slideSize:{width:1280,height:720}});
const navy='#13283E', teal='#087D83', gray='#45566A';
function text(s,value,x,y,w,h,size=26,color=navy,bold=false) {
  const t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  t.text=value;t.text.style={typeface:family,fontSize:size,bold,color,autoFit:'none'};
}
function slide(n,title,kicker='PROGRESS AND FINDINGS') {
  const s=p.slides.add();s.background.fill='#FFFFFF';
  text(s,'AI FOR FINANCIAL ANALYSIS ASSISTANT',64,32,1120,30,15,teal,true);
  text(s,title,64,96,1152,112,42,navy,true);
  text(s,kicker,64,216,1140,32,17,gray,true);
  text(s,'Internal prototype  ·  Evaluation uses synthetic company reports',64,670,1060,24,14,gray);
  text(s,String(n).padStart(2,'0'),1150,666,64,30,18,teal,true);
  s.speakerNotes.textFrame.setText('Fictional project scenario for the Chief of Staff demo. Findings describe the synthetic evaluation set, not results from real companies. Companion resources: Project Overview and Next Steps.');
  return s;
}
let s=slide(1,'A working prototype, with reliability work ahead');
text(s,'WORKING NOW',64,288,520,40,21,teal,true);
text(s,'Report summaries\nQuarter-to-quarter comparisons\nAnswers linked to source passages',64,352,535,185,29);
text(s,'BEFORE FINANCE REVIEW',692,288,520,40,21,teal,true);
text(s,'Preserve table periods and units\nVerify every numerical citation\nAgree on the first review questions',692,352,520,185,29);
text(s,'Leah Moreno is taking over product coordination.',64,592,1100,40,25,gray);
s=slide(2,'Simple reports work. Complex tables need repair.','WHAT WE LEARNED FROM THE TEST REPORTS');
text(s,'Clear narrative and single-column tables',64,290,1120,44,29,navy,true);
text(s,'The prototype finds the main figures and produces a useful first-pass summary.',64,344,1100,70,27,gray);
text(s,'Multi-column tables and inconsistent units',64,454,1120,44,29,navy,true);
text(s,'Period headers can attach to the wrong column. Some extracted figures lose\ntheir “thousands” or “millions” label, making comparisons unreliable.',64,510,1120,104,27,gray);
s=slide(3,'A source link is useful only if the figure checks out','CITATION AND COMPARISON GAPS');
text(s,'Observed failure',64,294,500,42,24,teal,true);
text(s,'A citation can reach the correct page\nbut point to the wrong row or period.\nA fluent summary can hide that error.',64,354,540,156,28);
text(s,'Required behavior',692,294,510,42,24,teal,true);
text(s,'Match each figure, unit and period\nto the cited source cell.\nFlag missing or conflicting evidence.',692,354,530,156,27);
text(s,'Analysts review and approve the output before sharing it.',64,584,1130,42,26,gray);
s=slide(4,'Leah’s first priority: define a review-ready build','NEXT STEPS');
const rows=[
 ['01','Reproduce the failures','Review the failing tables and citations with Engineering.'],
 ['02','Agree on the checks','Keep regression cases and define what must pass.'],
 ['03','Plan the finance review','Choose reviewers and questions before setting a date.'],
];
rows.forEach(([num,title,body],i)=>{
 const y=292+i*108;text(s,num,64,y,70,46,30,teal,true);text(s,title,160,y,1050,40,28,navy,true);text(s,body,160,y+44,1050,44,25,gray);
});
await fs.mkdir(BUILD_DIR,{recursive:true});
const candidatePath=path.join(BUILD_DIR,'candidate.pptx');
await(await PresentationFile.exportPptx(p)).save(candidatePath);
for(let i=0;i<4;i++) {
 const png=await p.export({slide:p.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(BUILD_DIR,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
const finalPath=path.join(BUILD_DIR,'final','financial-analysis-progress.pptx');
await fs.mkdir(path.dirname(finalPath),{recursive:true});
await finalizePresentation({workspaceDir:BUILD_DIR,candidatePath,finalPath,pythonExecutable:RUNTIME_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
 explicitTotalSlideCount:4,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
 fontPolicy:{basis:'design',families:[family]},verifyArtifactToolImport:true,
 receiptPath:path.join(BUILD_DIR,'validation.json')});
console.log(finalPath);
