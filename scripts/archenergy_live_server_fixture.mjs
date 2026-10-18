// SPDX-License-Identifier: GPL-3.0-or-later
// © 2026 ArchEnergy s.r.o.
// Import the existing APP implementation read-only; all state is in our QA folder.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';

const [appSource,qaRoot]=process.argv.slice(2);
const reverse=process.argv.includes('--reverse');
const fullSync=process.argv.includes('--full-sync');
if(!appSource||!qaRoot)throw new Error('Expected APP source and separate QA state directory');
const root=path.resolve(qaRoot),appRoot=path.resolve(appSource);
if(root===appRoot||root.startsWith(appRoot+path.sep))throw new Error('QA state must be outside original APP source');
fs.mkdirSync(root,{recursive:true});
const require=createRequire(path.join(appRoot,'package.json'));
const express=require('express');
const {Store}=await import(pathToFileURL(path.join(appRoot,'penb/server/store.mjs')));
const {LiveSketchup,mountLiveDevice}=await import(pathToFileURL(path.join(appRoot,'penb/server/live-sketchup.mjs')));
const {floorAreaFixture}=await import(pathToFileURL(path.join(appRoot,'penb/server/fixtures/floor-area-model.mjs')));
const {constructionProject}=await import(pathToFileURL(path.join(appRoot,'penb/shared/constructions.js')));
const store=new Store(root),project=store.create('EnergySketch isolated LIVE protocol QA');
if(fullSync)store.internal(project.id,p=>Object.assign(p,constructionProject({...p,...floorAreaFixture()})));
const live=new LiveSketchup(store,{authorize:async user=>user==='energysketch-qa',modelImportEnabled:reverse});
const {code}=live.issue(project.id,'energysketch-qa');
const app=express();
app.use(express.json({limit:'7mb'}));
let failed=false;
const batchHashes=[];
app.use((req,res,next)=>{
  // Keep the original outgoing/demo/import fixture on its original protocol;
  // the separate full-sync run exercises automatic reconciliation explicitly.
  if(!fullSync&&req.path.endsWith('/pair')&&Array.isArray(req.body?.capabilities))
    req.body.capabilities=req.body.capabilities.filter(c=>!['model-sync-v1','manual-sync-v1','report-layout-v1'].includes(c));
  if(req.method==='POST'&&req.path.endsWith('/batch')){
    batchHashes.push(createHash('sha256').update(JSON.stringify(req.body)).digest('hex'));
    if(!failed){failed=true;res.status(503).json({error:'Injected isolated QA outage'});return;}
  }
  next();
});
const api=express.Router();
mountLiveDevice(api,live);
app.use('/api/penb',api);
app.get('/qa/status',(_req,res)=>{
  const state=live.load(project.id);
  res.json({revision:state?.revision||0,entities:state?.entities?.length||0,
            summary:state?.summary||null,presence:state?.presence||null,
            firstRetryIdentical:batchHashes.length>=2&&batchHashes[0]===batchHashes[1],
            stats:state?.stats||{},modelImportEnabled:reverse,fullSync,sync:live.syncState(project.id),
            commands:(state?.commands||[]).map(c=>({...live.publicCommand(c),verification:c.verification||null,verificationError:c.verificationError||null}))});
});
app.post('/qa/enqueue',(req,res)=>{
  if(!reverse)throw new Error('Reverse QA was not explicitly enabled');
  const state=live.load(project.id),base={requestId:req.body.requestId,connectionId:state.connectionId,baseRevision:state.revision};
  if(fullSync&&req.body.action==='sync_model'){
    const p=store.get(project.id);
    store.change(project.id,p.revision,'EnergySketch isolated addressed edit',actual=>{
      const f=actual.model.faces.find(f=>!f.id.startsWith('epcp_')&&!f.hostFaceId);
      if(req.body.edit==='remove')actual.model.faces=actual.model.faces.filter(v=>v.id!==f.id);
      else if(req.body.edit==='color')actual.constructions.find(c=>c.id===f.constructionId).color='#ef4217';
      else for(const face of actual.model.faces)if(face.zoneId===f.zoneId)
        face.rings=face.rings.map(r=>r.map(p=>[p[0]+100,p[1],p[2]]));
    });
    res.json({queued:true});
  }else if(fullSync&&['import_model','floor-report','floor-report-layout'].includes(req.body.action)){
    const p=store.get(project.id);
    res.json(live.enqueueModel(project.id,{...base,projectRevision:p.revision,version:'accepted',
      ...(req.body.action==='import_model'?{}:{content:req.body.action})}));
  }else if(req.body.action==='import_model'){
    const p=store.internal(project.id,actual=>Object.assign(actual,floorAreaFixture()));
    const wall=p.model.faces.find(f=>f.id==='a-wall-0'),hole=[[1000,0,1000],[1000,0,2000],[2000,0,2000],[2000,0,1000]];
    wall.rings.push(hole);p.model.faces.push({...wall,id:'a-window',kind:'window',thicknessMm:null,hostFaceId:wall.id,rings:[hole.slice().reverse()]});
    store.internal(p.id,actual=>Object.assign(actual,p));
    res.json(live.enqueueModel(project.id,{...base,projectRevision:p.revision,version:'accepted'}));
  }else res.json(live.enqueue(project.id,{...base,action:req.body.action}));
});
app.use((err,_req,res,_next)=>res.status(err.status||500).json({error:err.message}));
const server=app.listen(0,'127.0.0.1',()=>{
  // Pipe-only handshake; the parent must never write the one-time code to a log.
  process.stdout.write(JSON.stringify({origin:`http://127.0.0.1:${server.address().port}`,code})+'\n');
});
process.stdin.once('data',()=>server.close(()=>process.exit(0)));
process.stdin.once('end',()=>server.close(()=>process.exit(0)));
