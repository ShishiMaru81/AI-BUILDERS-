'use client';
import Link from 'next/link';
import {useEffect,useRef,useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {ArrowRight,Camera,CheckCircle2,Download,ImagePlus,Leaf,LoaderCircle,MessageCircle,ScanLine,Trash2} from 'lucide-react';
import {API,ApiError,download,formatTime,getSessionToken,request} from '@/lib/api';
import {DoctorFollowUp} from './doctor-follow-up';
import {FarmerQuestions, FarmerActionCard} from './farmer-guidance';
import {initialFarmerContext} from '@/lib/farmer-guidance';
import {cropGuides,potatoFieldChecks} from '@/lib/doctor-guidance';
import type {Case,DoctorCapabilities,DoctorScreening,FarmerContext,Farm,Plot} from '@/lib/types';

type Locale='en'|'bn';
type Perform=(fn:()=>Promise<unknown>,message?:string)=>Promise<void>;
export function conditionName(label:string){return label.split('___').pop()!.replaceAll('_',' ').replace(/\s+/g,' ').trim()}
export function cropName(id:string,capabilities?:DoctorCapabilities,locale:Locale='en'){
 const crop=capabilities?.crops.find(c=>c.id===id);
 return crop?(locale==='bn'?crop.name_bn:crop.name_en):id.replaceAll('_',' ');
}
export function useDoctorCapabilities(){return useQuery({queryKey:['doctor-capabilities'],queryFn:()=>request<DoctorCapabilities>('/doctor/capabilities'),staleTime:60000,retry:1})}
const screeningCropIds = new Set(['tomato', 'potato']);

// The parent keys this component by plot identity. A context change unmounts it,
// aborts the request and discards all local photo/result state together.
export function DoctorStudio({plot,plots,plotsLoading,farms,farmStatus,retryFarms,onSelectPlot,cases,casesTotal,casesHasMore,casesFetching,casesError,onLoadMore,locale}: {
 plot?:Plot;plots:Plot[];plotsLoading:boolean;farms:Farm[];farmStatus:'pending'|'error'|'success';retryFarms:()=>void;onSelectPlot:(id:string)=>void;cases:Case[];casesTotal:number;
 casesHasMore:boolean;casesFetching:boolean;casesError?:string;onLoadMore:()=>void;locale:Locale;
}){
 const {data:capabilities,error:catalogError,isFetching:catalogFetching,refetch}=useDoctorCapabilities();
 const qc=useQueryClient();const t=(en:string,bn:string)=>locale==='bn'?bn:en;
 const [crop,setCrop]=useState(plot&&screeningCropIds.has(plot.crop)?plot.crop:'tomato');const [file,setFile]=useState<File>();
 const [part,setPart]=useState<'leaf'|'other'>('leaf');
 const [context,setContext]=useState<FarmerContext>();
 const [canRetryLeaf,setCanRetryLeaf]=useState(false);
 const [symptoms,setSymptoms]=useState('');const [result,setResult]=useState<DoctorScreening>();
 const [error,setError]=useState('');const [pending,setPending]=useState(false);
 const [plotName,setPlotName]=useState('');const [farmId,setFarmId]=useState(farms[0]?.id||'');
 const [area,setArea]=useState('1');const [creating,setCreating]=useState(false);const [preview,setPreview]=useState('');
 const input=useRef<HTMLInputElement>(null);const camera=useRef<HTMLInputElement>(null);
 const flight=useRef<AbortController|null>(null);const generation=useRef(0);const locked=useRef(false);
 const screeningCrops=capabilities?.crops.filter(c=>screeningCropIds.has(c.id));
 const capability=screeningCrops?.find(c=>c.id===crop);
 const matching=plots.filter(p=>p.crop===crop);const matches=plot?.crop===crop;
 const vision=capabilities?.provider==='groq';
 const isProduce=vision?context?.kind==='produce':part==='other';
 const researchProduce=capabilities?.research_produce_model?.available&&
  (crop==='tomato'||crop==='potato')&&isProduce;
 const normalScreening=!!capability?.available&&(vision||part==='leaf');
 const showUpload=vision||part==='leaf'||researchProduce;
 const canResearch=capabilities?.research_leaf_model?.available&&
  (crop==='tomato'||crop==='potato')&&!isProduce;
 const canChoose=showUpload&&!plotsLoading&&(normalScreening||canResearch||researchProduce);
 useEffect(()=>()=>{generation.current++;flight.current?.abort()},[]);
 useEffect(()=>{
  if(!file)return;
  const url=URL.createObjectURL(file);setPreview(url);
  return ()=>URL.revokeObjectURL(url);
 },[file]);
 function clearPhoto(){setCanRetryLeaf(false);setFile(undefined);setPreview('');setResult(undefined);setError('');if(input.current)input.current.value='';if(camera.current)camera.current.value=''}
 function changeCrop(value:string){generation.current++;flight.current?.abort();clearPhoto();setContext(undefined);setSymptoms('');setCrop(value)}
 function choose(value?:File){
  if(locked.current||!canChoose||!value)return;
  if(!value.size||value.size>8*1024*1024||!['image/jpeg','image/png','image/webp'].includes(value.type)){
   clearPhoto();setError(t('Choose a non-empty JPG, PNG or WebP photo up to 8 MB.','৮ মেগাবাইটের মধ্যে JPG, PNG বা WebP ছবি দিন।'));return;
  }
  setError('');setCanRetryLeaf(false);setResult(undefined);setFile(value);
 }
 async function screen(mode:'auto'|'local_leaf'|'research_leaf'|'research_produce'='auto'){
  const researchLeaf=mode==='research_leaf';
  const produce=mode==='research_produce';
  const research=researchLeaf||produce;
  const localLeaf=mode==='local_leaf';
  const enabled=researchLeaf?canResearch:produce?researchProduce:normalScreening;
  if(locked.current||!file||!canChoose||creating||!enabled)return;
  locked.current=true;setPending(true);setError('');setResult(undefined);
  const current=++generation.current;const controller=new AbortController();flight.current=controller;
  const selection = localLeaf||researchLeaf ? initialFarmerContext : context;
  if(localLeaf) setContext(selection);
  setCanRetryLeaf(false);
  const form=new FormData();
  form.append('image',file);
  form.append('crop',crop);
  form.append('locale',locale);
  const cloudPart = selection?.kind === 'produce' ? 'other' : selection?.kind ?? 'auto';
  form.append('plant_part',researchLeaf?'leaf':produce?'other':vision?cloudPart:part);
  if(mode!=='auto') form.append('screening_mode',mode);
  if(selection) form.append('farmer_context',JSON.stringify(selection));
  if(!research && matches && plot){
   form.append('plot_id',plot.id);
   form.append('symptoms',symptoms);
  }
  try{
   const response=await request<DoctorScreening>('/doctor/cases',{method:'POST',body:form,signal:controller.signal});
   if(current===generation.current&&!controller.signal.aborted){setResult(response);if(!research&&matches){await qc.invalidateQueries({queryKey:['cases']});await qc.invalidateQueries({queryKey:['actions']})}}
  }catch(e){
   if(current===generation.current&&!controller.signal.aborted){
    setError((e as Error).message);
    setCanRetryLeaf(vision && !selection && e instanceof ApiError && e.code==='VISION_UNAVAILABLE');
   }
  }
  finally{if(current===generation.current){locked.current=false;setPending(false)}}
 }
 const selectedFarmId=farms.find(f=>f.id===farmId)?.id || farms[0]?.id || '';
 async function createFirstFarm(event:React.FormEvent<HTMLFormElement>){
  event.preventDefault();
  if(creating || pending)return;
  const fields=new FormData(event.currentTarget);
  setCreating(true);setError('');
  try{
   const farm=await request<Farm>('/farms',{method:'POST',body:JSON.stringify({
    name:String(fields.get('name')).trim(),district:String(fields.get('district')).trim()
   })});
   qc.setQueryData<Farm[]>(['farms'],previous=>[...(previous||[]).filter(f=>f.id!==farm.id),farm]);
   setFarmId(farm.id);
   void qc.invalidateQueries({queryKey:['farms']});
  }catch(e){setError((e as Error).message)}finally{setCreating(false)}
 }
 async function createPlot(){
  if(locked.current||creating||!plotName.trim()||!selectedFarmId)return;
  setCreating(true);setError('');
  const current=++generation.current;
  try{
   const created=await request<Plot>('/plots',{method:'POST',body:JSON.stringify({farm_id:selectedFarmId,name:plotName.trim(),crop,area_acres:area,stage:'Vegetative'})});
   await qc.invalidateQueries({queryKey:['plots']});
   if(current===generation.current)onSelectPlot(created.id);
  }catch(e){if(current===generation.current)setError((e as Error).message)}finally{if(current===generation.current)setCreating(false)}
 }
 return <><div className="studio-grid"><section className="panel upload-panel">
  <div className="section-heading"><div><span className="eyebrow">CROP HEALTH STUDIO</span><h2>{vision?t('Upload a leaf or vegetable photo','পাতা বা সবজির ছবি দিন'):t('Choose a crop, then upload a leaf photo.','ফসল বেছে নিন, তারপর পাতার ছবি আপলোড করুন')}</h2></div><span className="badge">{vision?'Groq Vision':screeningCrops?`${screeningCrops.length} ${t('crop groups','ফসল')}`:t('Loading crops…','ফসল লোড হচ্ছে…')}</span></div>
  <div className="form-grid"><label>{t('Crop','ফসল')}<select aria-label="Screening crop" value={crop} disabled={pending||creating||plotsLoading||!capabilities} onChange={e=>changeCrop(e.target.value)}>
   {screeningCrops?.map(c=><option key={c.id} value={c.id}>{c.name_en} · {c.name_bn}{c.available?'':` (${t('unavailable','অনুপলব্ধ')})`}</option>)}
  </select></label><label>{t('Selected plot','নির্বাচিত জমি')}<select aria-label="Screening plot" disabled={pending||creating} value={matches?plot?.id:''} onChange={e=>{if(e.target.value)onSelectPlot(e.target.value)}}><option value="">{t('Choose a matching plot','মিল থাকা জমি বেছে নিন')}</option>{matching.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label></div>
  {!vision&&<label>{t('Affected plant part','আক্রান্ত অংশ')}
   <select aria-label="Affected plant part" value={part} disabled={pending||creating} onChange={e=>{
    clearPhoto();
    setPart(e.target.value==='other'?'other':'leaf');
   }}>
    <option value="leaf">{t('Leaf','পাতা')}</option>
    <option value="other">{crop==='potato'?t('Potato tuber (the potato itself)','আলু (কন্দ)'):t('Fruit, tuber, stem or other part','ফল, কন্দ, কাণ্ড বা অন্য অংশ')}</option>
   </select>
  </label>}
  {!showUpload?<PlantPartGuide crop={crop} locale={locale}/>:<>
  {capability&&!matches&&<div className="notice"><div><strong>{t('Screen now or select a plot to save your observation.','এখন পরীক্ষা করুন, অথবা ফল সংরক্ষণ করতে জমি বেছে নিন।')}</strong><p>{t('You can save screenings to a plot growing the selected crop.','নির্বাচিত ফসলের জমিতে পরীক্ষার ফল সংরক্ষণ করা যাবে।')}</p>{!matching.length&&(
   farmStatus==='pending' ? <p role="status">{t('Loading your farms…','আপনার খামার লোড হচ্ছে…')}</p> :
   farmStatus==='error' ? <div role="alert"><p>{t('Your farms could not be loaded.','আপনার খামারের তালিকা লোড করা যায়নি।')}</p><button type="button" className="btn secondary" onClick={retryFarms}>{t('Retry loading farms','আবার খামারের তালিকা লোড করুন')}</button></div> :
   !farms.length ? <form onSubmit={createFirstFarm}>
    <p>{t('Create your first farm to save a crop plot.','ফসলের জমি সংরক্ষণ করতে প্রথমে আপনার খামার তৈরি করুন।')}</p>
    <label>{t('Farm name','খামারের নাম')}<input name="name" required maxLength={100}/></label>
    <label>{t('Farm district','খামারের জেলা')}<input name="district" required maxLength={80}/></label>
    <button className="btn secondary" disabled={creating||pending}>{t('Create farm','খামার তৈরি করুন')}</button>
   </form> :
   <form onSubmit={e=>{e.preventDefault();void createPlot()}}><label>{t('Farm','খামার')}<select aria-label="New crop plot farm" value={selectedFarmId} onChange={e=>setFarmId(e.target.value)}>{farms.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}</select></label><label>{t('Plot name','জমির নাম')}<input aria-label="New crop plot name" required maxLength={100} value={plotName} onChange={e=>setPlotName(e.target.value)}/></label><label>{t('Area (acres)','ক্ষেত্রফল (একর)')}<input aria-label="New crop plot area" type="number" required min="0.01" max="10000" step="0.01" value={area} onChange={e=>setArea(e.target.value)}/></label><button className="btn secondary" disabled={pending||creating||!farms.length||!plotName.trim()}>{creating?t('Creating…','তৈরি হচ্ছে…'):t('Create crop plot','ফসলের জমি তৈরি করুন')}</button></form>)}</div></div>}
  {catalogError&&<div className="error" role="alert">{t('Could not load crop capabilities.','ফসলের তালিকা লোড হয়নি।')} <button onClick={()=>void refetch()}>{t('Retry','আবার চেষ্টা')}</button></div>}
  {capability&&!capability.available&&<p className="error" role="alert">{t('Model unavailable for this crop.','এই ফসলের মডেল অনুপলব্ধ।')} {t('Install and verify its pinned model bundle before screening.','পরীক্ষার আগে মডেল ইনস্টল ও যাচাই করুন।')}</p>}
  <div className={`dropzone ${preview?'has-image':''}`} aria-busy={pending} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!locked.current)choose(e.dataTransfer.files[0])}}>
   {preview ? <span className="doctor-preview ui-reveal" key={preview} data-checking={pending}>
     <img src={preview} alt={vision?t('Selected crop photo','নির্বাচিত ফসলের ছবি'):t('Selected leaf for screening','পরীক্ষার জন্য নির্বাচিত পাতার ছবি')}/>
   </span> : <><div className="upload-symbol"><ImagePlus size={35}/></div><h3>{t('A clear photo is a good beginning.','পরিষ্কার ছবি দিয়ে শুরু করুন।')}</h3><p>{vision?t('Choose a photo that shows the affected area.','আক্রান্ত অংশ দেখা যায় এমন একটি ছবি দিন।'):t('Drop one leaf photo here, or choose from your device.','পাতার একটি ছবি দিন অথবা ডিভাইস থেকে বেছে নিন।')}</p></>}
   <div className="row"><button className="btn primary" disabled={pending||!canChoose} onClick={()=>input.current?.click()}><ImagePlus size={16}/>{t(preview?'Change photo':'Choose a photo',preview?'ছবি পরিবর্তন':'ছবি বেছে নিন')}</button><button className="btn secondary" disabled={pending||!canChoose} onClick={()=>camera.current?.click()}><Camera size={16}/>{t('Camera','ক্যামেরা')}</button>{file&&<button className="text-link" disabled={pending} onClick={clearPhoto}>{t('Remove','সরান')}</button>}</div>
   <input ref={input} aria-label={vision?t('Upload crop photo','ফসলের ছবি দিন'):'Upload leaf photo'} type="file" accept="image/jpeg,image/png,image/webp" hidden disabled={pending||!canChoose} onChange={e=>{choose(e.target.files?.[0]);e.target.value=''}}/>
   <input ref={camera} aria-label={vision?t('Take a crop photo','ফসলের ছবি তুলুন'):'Take a leaf photo'} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" hidden disabled={pending||!canChoose} onChange={e=>{choose(e.target.files?.[0]);e.target.value=''}}/>
   <small>{t('JPG, PNG or WebP · Up to 8 MB · Private storage','JPG, PNG বা WebP · সর্বোচ্চ ৮ মেগাবাইট · ব্যক্তিগত সংরক্ষণ')}</small>
  </div>
  {vision&&<p className="helper">{canResearch||researchProduce
    ?t('Standard screening sends the photo to Groq. The research preview runs locally.','সাধারণ পরীক্ষায় ছবিটি গ্রক-এ যায়। গবেষণার পরীক্ষা স্থানীয়ভাবে চলে।')
    :t('Screening sends this photo to Groq for analysis. The app removes photo metadata first.', 'পরীক্ষার জন্য ছবিটি গ্রক-এ পাঠানো হবে। আগে ছবির মেটাডেটা সরানো হয়।')}</p>}
  <FarmerQuestions value={context} disabled={pending||creating} locale={locale} leafOnly={!vision}
    onChange={value=>{setContext(value);setCanRetryLeaf(false);setResult(undefined);setError('')}}/>
  {matches&&<label>{vision?t('Private plot note (optional)','জমির ব্যক্তিগত নোট (ঐচ্ছিক)'):t('What have you noticed? (Optional)','কী লক্ষণ দেখেছেন? (ঐচ্ছিক)')}<textarea maxLength={2000} disabled={pending} value={symptoms} onChange={e=>setSymptoms(e.target.value)} placeholder={t('Spots, yellowing, when symptoms began…','দাগ, হলুদ পাতা, লক্ষণ শুরুর সময়…')}/></label>}
  {error&&<div className="error" role="alert"><p>{error}</p>
   {canRetryLeaf&&<button type="button" className="btn secondary" disabled={pending||!file} onClick={()=>void screen('local_leaf')}>
    {t('This is a leaf · use local screening','এটি পাতার ছবি · স্থানীয় মডেল দিয়ে পরীক্ষা করুন')}
   </button>}
  </div>}
  {(vision||part==='leaf')&&<button className="btn primary full" disabled={!file||!canChoose||!normalScreening||pending||creating||catalogFetching&&!capabilities} onClick={()=>void screen()}>{pending?<LoaderCircle size={18} className="spin"/>:<ScanLine size={18}/>} {pending?t('Checking image…','ছবি পরীক্ষা হচ্ছে…'):matches?t('Screen & save observation','পরীক্ষা করুন ও সংরক্ষণ করুন'):t('Screen photo','ছবি পরীক্ষা করুন')}<ArrowRight size={17}/></button>}
  {canResearch&&<button type="button" className="btn secondary full" disabled={!file||pending||creating||!canChoose}
   onClick={()=>void screen('research_leaf')}>{t('Preview with research leaf model','গবেষণার পাতার মডেল দিয়ে পরীক্ষা করুন')}</button>}
  {researchProduce&&<button type="button" className="btn secondary full" disabled={!file||pending||creating||!canChoose}
   onClick={()=>void screen('research_produce')}>{t('Preview with research produce model','গবেষণার ফল ও কন্দের মডেল দিয়ে পরীক্ষা করুন')}</button>}
  {!vision&&part==='leaf'&&<p className="helper">{t('Research screening only. Confirm the crop yourself. Unknown diseases and non-leaf images may receive high scores; this is not a diagnosis.','এটি গবেষণা পর্যায়ের সহায়তা। ফসল নিজে নিশ্চিত করুন। অজানা রোগ বা পাতাবিহীন ছবিতেও বেশি স্কোর আসতে পারে; এটি নিশ্চিত রোগ নির্ণয় নয়।')}</p>}
  {!vision&&part==='leaf'&&capability&&<details><summary>{t('Supported conditions & limits','সমর্থিত অবস্থা ও সীমাবদ্ধতা')} ({capability.labels.length})</summary><p>{capability.labels.map(conditionName).join(' · ')}</p>{!capability.has_healthy_class&&<p className="error">{t('This crop has no healthy reference class. A healthy leaf cannot be ruled in or out.','এই ফসলের সুস্থ পাতার শ্রেণি নেই। সুস্থ কি না নিশ্চিত করা যায় না।')}</p>}<small>{capability.model_version} · {t('Not field-validated','মাঠ পর্যায়ে যাচাই করা হয়নি')}</small></details>}
 </>}</section>{showUpload&&<div className="stack">{result?<DoctorResult result={result} locale={locale} originalFile={file} onUpdate={setResult}/>:<section className="panel result-placeholder"><ScanLine size={38}/><h3>{t('Room for understanding.','ফসলকে বোঝার সুযোগ।')}</h3><p>{t('Your screening, possible conditions, model evidence and next steps will appear here.','পরীক্ষার ফল, সম্ভাব্য অবস্থা ও পরবর্তী করণীয় এখানে দেখুন।')}</p><span className="badge amber">{t('Uncertainty is part of the result','ফলাফলে অনিশ্চয়তা থাকে')}</span></section>}<section className="panel"><h3>{t('Photograph the affected area','আক্রান্ত অংশের ছবি তুলুন')}</h3>{[t('Use natural, even light.','প্রাকৃতিক ও সমান আলো ব্যবহার করুন।'),t('Get close and keep the camera steady.','কাছ থেকে স্থির ক্যামেরায় ছবি নিন।'),t('Include healthy tissue next to the damaged area.','আক্রান্ত অংশের পাশের সুস্থ অংশও ছবিতে রাখুন।'),t('Avoid filters and distracting backgrounds.','ফিল্টার ও জটিল পটভূমি এড়িয়ে চলুন।')].map((tip,i)=><div className="tip" key={tip}><span>{i+1}</span>{tip}</div>)}</section></div>}</div>
 <section className="panel"><h2>{t('Recent screenings','সাম্প্রতিক পরীক্ষা')} · {casesTotal}</h2>{casesError&&<p className="error" role="alert">{casesError}</p>}{casesFetching&&!cases.length?<p role="status">{t('Loading screenings…','পরীক্ষা লোড হচ্ছে…')}</p>:<CaseList cases={cases} locale={locale}/>}<CasePagination total={casesTotal} shown={cases.length} hasMore={casesHasMore} pending={casesFetching} onLoadMore={onLoadMore}/></section></>;
}

function PlantPartGuide({crop,locale}:{crop:string;locale:Locale}){
 const t=(en:string,bn:string)=>locale==='bn'?bn:en;
 if(crop!=='potato')return <div className="stack">
  <h3>{t('What to document','?? ???????? ?????')}</h3>
  <p>{t('Take a close-up of the affected area and a wider photo of the whole plant. Note when the damage started and whether it is spreading. Share these with your local agricultural extension office.','???????? ????? ??? ???? ??? ???? ????? ??? ?????? ????? ??? ???? ?????? ??? ???????? ?? ?? ???? ???????? ???? ?????????? ????? ??????')}</p>
  <p>{t('Select Leaf to screen an affected leaf with the model.','???? ????? ???????? ???? ??????? ???? ???? ???? ????')}</p>
 </div>;
 return <div className="stack">
  <h3>{t('Potato tuber rot guide','???? ???? ??? ???????? ??????????')}</h3>
  <p>{t('Use these signs to narrow down what to report. Tuber checks are based on what you observe. The image model screens leaves.','???? ??????????? ?? ??????? ?? ????? ????? ????? ??????? ?????? ?????? ?????????? ????? ???????????? ??? ?????? ???? ?????? ????? ??? ??????? ????')}</p>
  <ul>
   <li>{t('Dry, sunken or wrinkled patches with white fuzz can fit Fusarium dry rot. Late blight can also cause dark sunken patches, especially if the field showed rapidly spreading leaf blight.','?????, ??? ?????? ?? ?????? ?????? ???? ???? ?????? ????? ??????????? ????? ??? ??? ????? ????? ????? ??? ????? ?????? ????? ??? ?????? ??? ???? ?????? ??? ?????')}</li>
   <li>{t('Wet, mushy or leaking tissue suggests soft rot or secondary decay.','????, ??? ?? ?? ??? ??? ??? ??? ?? ??????? ????????? ????? ??? ?????')}</li>
  </ul>
  <h4>{t('What to do now','??? ?? ?????')}</h4>
  <p>{t('Discard visibly moldy or rotting potatoes. Keep them out of food, sale and seed lots. Check nearby potatoes, clean the storage bin and keep sound potatoes dry and ventilated. If several tubers are affected or field symptoms are spreading, contact your local agricultural extension office.','???????? ??????????? ?? ??? ??? ???? ???? ?????, ?????? ? ????? ??? ???? ????? ?????? ????? ??? ??????? ????, ????? ???????? ???? ??? ???? ??? ????? ? ????? ????? ??? ??? ?????? ?????? ?????? ??? ???????? ??? ?? ????? ????? ?????? ???????? ???? ?????????? ????? ??????? ?????')}</p>
  <a href="https://apps.extension.umn.edu/garden/diagnose/plant/vegetable/potato/tuberwhitefuzz.html" target="_blank" rel="noreferrer">{t('Tuber symptom reference','?????? ??????? ??????????')}</a>
  <a href="https://blog-fruit-vegetable-ipm.extension.umn.edu/2019/10/potatoes-post-harvest-disorders-and.html" target="_blank" rel="noreferrer">{t('Potato storage and rot guidance','??? ??????? ? ???? ??????????')}</a>
 </div>;
}

export function DoctorResult({result,locale='en',imgUrl,imgError,originalFile,onUpdate}:{result:DoctorScreening;locale?:Locale;imgUrl?:string;imgError?:string;originalFile?:File;onUpdate?:(updated:DoctorScreening)=>void}){
 const t=(en:string,bn:string)=>locale==='bn'?bn:en;const {data:capabilities}=useDoctorCapabilities();
 const produceResearch=result.model.model_id==='agrodoctor-research-produce';
 const submittedPhoto=imgUrl&&<img src={imgUrl} alt={produceResearch||result.assessment?t('Submitted crop photo','জমা দেওয়া ফসলের ছবি'):t('Submitted leaf photo','জমা দেওয়া পাতার ছবি')} style={{width:'100%',maxHeight:260,objectFit:'contain'}}/>;
 if(produceResearch){
  const damage=result.classification.top_label.endsWith('___Visible_damage');
  return <section className="panel result ui-reveal" aria-label="Screening result">
   {submittedPhoto}{imgError&&<p role="status">{imgError}</p>}
   <span className="badge amber">{t('Research produce preview','ফল ও কন্দের গবেষণামূলক পরীক্ষা')}</span>
   <h2>{result.classification.abstained?t('Unable to assess visible damage','দৃশ্যমান ক্ষতি বোঝা যায়নি'):
    damage?t('Possible visible damage or decay','সম্ভাব্য দৃশ্যমান ক্ষতি বা পচন'):
    t('The visible surface resembles sound produce','দৃশ্যমান অংশটি সুস্থ ফল বা কন্দের মতো দেখাচ্ছে')}</h2>
   <p>{t('A photo cannot confirm the cause or tell you whether the produce is safe to eat.','ছবি দেখে ক্ষতির কারণ বা খাওয়া নিরাপদ কি না নিশ্চিত করা যায় না।')}</p>
   <h3>{t('What to check next','এরপর কী দেখবেন')}</h3>
   <ul><li>{t('Turn the item over and photograph it in even light.','ফল বা কন্দটি উল্টে সমান আলোতে ছবি তুলুন।')}</li>
   <li>{t('Set visibly damaged items aside and check others from the same batch.','ক্ষতিগ্রস্ত ফল বা কন্দ আলাদা করে একই ব্যাচের বাকিগুলো দেখুন।')}</li></ul>
   <div className="model-evidence"><strong>{result.model.version}</strong></div>
  </section>;
 }
 const askAboutResult=()=>{
  const finding=result.assessment;
  const observation=finding?[finding.subject,...finding.signs,finding.uncertainty].filter(Boolean).join(' '):
    result.classification.abstained?t('Inconclusive screening','পরীক্ষায় নির্দিষ্ট ফল পাওয়া যায়নি'):conditionName(result.classification.top_label);
  const draft=result.id?undefined:t('My unsaved AgroDoctor screening says','অ্যাগ্রোডক্টরের অসংরক্ষিত পরীক্ষায় দেখা গেছে')+' — '+observation.slice(0,900)+' '+t('What should I check next?','এরপর কী দেখব?');
  window.dispatchEvent(new CustomEvent('agrosphere:open-farmer-chat',{detail:{caseId:result.id,plotId:result.plot_id??undefined,draft}}));
 };
 const chatButton=<button type="button" className="btn secondary" onClick={askAboutResult}><MessageCircle size={16}/>{t('Ask about this screening','এই পরীক্ষার ফল নিয়ে প্রশ্ন করুন')}</button>;
 const potatoChecks=result.crop==='potato'&&(!result.assessment||result.assessment.part==='leaf')&&
  <details>
   <summary>{t('Check for other potato leaf problems','আলুর পাতার অন্যান্য সমস্যা দেখুন')}</summary>
   <p>{t('Compare these signs on the plant. These checks can help you decide what to photograph and show an adviser.','গাছে এই লক্ষণগুলো মিলিয়ে দেখুন। কী ছবি তুলবেন ও কৃষি কর্মকর্তাকে কী দেখাবেন, তা বুঝতে এই লক্ষণগুলো সহায়তা করবে।')}</p>
   {potatoFieldChecks.map(({source,...translations})=>{
    const check=translations[locale];
    return <div key={source}>
     <h4>{check.title}</h4>
     <p>{check.signs}</p>
     <p>{check.action}</p>
     <a href={source} target="_blank" rel="noreferrer">{t('Read the field guide','মাঠ নির্দেশিকা পড়ুন')}</a>
    </div>;
   })}
  </details>;
 if(result.assessment){
  const a=result.assessment;
  const heading=a.outcome==='possible_condition'
   ? (a.condition?t('Possible condition','সম্ভাব্য অবস্থা')+' · '+a.condition:a.pattern||result.classification.top_label)
   : a.outcome==='no_visible_damage'?t('No visible damage','দৃশ্যমান ক্ষতি নেই')
   : a.outcome==='unrelated'?t('No assessable crop in this photo','ছবিতে পরীক্ষার উপযোগী ফসল নেই')
   : a.signs.length && a.pattern ? a.pattern : t('The cause is unclear','কারণ স্পষ্ট নয়');
  return <section className="panel result ui-reveal" aria-label="Screening result">
   {submittedPhoto}
   {imgError&&<p role="status">{imgError}</p>}
   <span className="badge">Groq Vision · {a.subject}</span>
   <p>{result.plot_name||t('Screening preview','পরীক্ষার প্রাথমিক ফল')}</p>
   {result.save_notice&&<p role="status">{t('This result was not saved because the photo could not be matched to this plot.','ছবির ফসল জমির সঙ্গে মেলানো যায়নি। ফলটি শুধু এখানে দেখানো হচ্ছে।')}</p>}
   <h2>{heading}</h2>
   {a.signs.length>0&&<><h3>{t('Visible signs','দৃশ্যমান লক্ষণ')}</h3>
    <ul>{a.signs.map((sign,i)=><li key={i}>{sign}</li>)}</ul></>}
   <h3>{t('What could explain this','সম্ভাব্য কারণ')}</h3><p>{a.explanation}</p>
   <p><strong>{t('What remains uncertain','যা এখনও অনিশ্চিত')}</strong> · {a.uncertainty}</p>
   {a.field_check&&<div>
    <h3>{t('What to check in the field','মাঠে কী মিলিয়ে দেখবেন')}</h3>
    <p>{a.field_check.possible_explanation}</p>
    <p>{a.field_check.next_check}</p>
    <a href={a.field_check.source_url} target="_blank" rel="noreferrer">{t('Field reference','মাঠ নির্দেশিকা')}</a>
   </div>}
   <FarmerActionCard result={result} locale={locale}/>
   {chatButton}
   {(capabilities?.provider==='groq'||result.photo_count===2)&&<DoctorFollowUp key={result.id??'preview'}
     result={result} locale={locale} originalFile={originalFile} onUpdate={onUpdate}/>}
   <details><summary>{t('More checks from the photo','ছবি অনুযায়ী আরও যা দেখবেন')}</summary>
    <ul>{result.advice.map((step,i)=><li key={i}>{step}</li>)}</ul></details>
   {potatoChecks}
   <div className="model-evidence"><strong>{result.model.version}</strong><p>{t('Photo-based screening. An agricultural extension officer can help confirm the cause.','এটি ছবিভিত্তিক প্রাথমিক পরীক্ষা। কারণ নিশ্চিত করতে কৃষি কর্মকর্তার সহায়তা নিন।')}</p></div>
  </section>;
 }
 const {classification}=result;
 const cropOptions=classification.selected_crop_options??[];
 const guide=cropGuides[result.crop||'tomato'];
 const condition=classification.top_label.split('___').pop()!;
 const guidance=classification.abstained?undefined:guide?.conditions[condition];
 const healthy=!classification.abstained&&condition.toLowerCase()==='healthy';
 const blightPattern=classification.rejection_reason==='conflicting_leaf_views'&&classification.pattern_hint==='blight_like';
 const comparedLabels=blightPattern ? ['Late_blight', 'Early_blight']
  : classification.rejection_reason==='low_confidence' ? cropOptions.slice(0,2).map(option=>option.label.split('___').pop()!) : [];
 const visibleChecks=classification.abstained&&guide ? comparedLabels.filter(label=>Object.hasOwn(guide.conditions,label)) : [];
 const reasons:Record<string,string>={
  class_disabled:t('This condition did not have enough validation evidence for a named result.','এই অবস্থার নাম বলার জন্য যাচাইয়ের তথ্য যথেষ্ট ছিল না।'),
  conflicting_leaf_views:blightPattern
   ? t('The center and the full photo resembled different blight references. Photograph both sides of an affected leaf and the stem next to healthy tissue.','ছবির মাঝের অংশ ও পুরো ছবি ভিন্ন ধরনের ধসা রোগের নমুনার সঙ্গে মিলেছে। একটি আক্রান্ত পাতার দুই পিঠ ও সুস্থ অংশসহ কাণ্ডের ছবি তুলুন।')
   : t('The center and the full photo gave different results. Photograph one affected leaf against a plain background.','ছবির মাঝের অংশ ও পুরো ছবির ফল মেলেনি। সাদামাটা পটভূমিতে একটি আক্রান্ত পাতার ছবি তুলুন।'),
  crop_mismatch:t('The model’s closest match was a different crop. Keep your crop selection if it is correct. Take a new photo with one affected leaf filling the frame.','মডেলটি অন্য ফসলের ছবির সঙ্গে বেশি মিল পেয়েছে। নির্বাচিত ফসল সঠিক হলে সেটিই রাখুন। একটি আক্রান্ত পাতা দিয়ে ফ্রেম ভরে নতুন ছবি তুলুন।'),model_disagreement:t('The two screening models disagreed. Ask an adviser to review the leaf.','দুটি মডেলের ফল মেলেনি। পাতাটি একজন কৃষি কর্মকর্তাকে দেখান।'),unconfirmed_leaf_screen:t('A second screening could not confirm the first result.','দ্বিতীয় পরীক্ষায় প্রথম ফলটি নিশ্চিত করা যায়নি।'),low_confidence:t('The model score did not meet the research screening threshold.','মডেলের স্কোর পরীক্ষার সীমা পূরণ করেনি।'),image_quality:t('The photo quality checks did not pass. Take a clearer photo.','ছবির মান যথেষ্ট নয়। আরও পরিষ্কার ছবি নিন।')};
 return <section className="panel result ui-reveal" aria-label="Screening result">
  {submittedPhoto}{imgError&&<p role="status">{imgError}</p>}
  <span className="badge amber">{result.model.model_id==='agrodoctor-research-leaf'
   ?t('Research leaf preview','গবেষণার পাতার মডেলের পরীক্ষা')
   :result.fallback_reason==='vision_unavailable'?t('Local leaf screening','স্থানীয় পাতার মডেলের পরীক্ষা'):result.meta.mode} · {cropName(result.crop||'tomato',capabilities,locale)}</span><p>{result.plot_name||result.plot_id||t('Screening preview','পরীক্ষার প্রাথমিক ফল')}</p>
  {result.fallback_reason==='vision_unavailable'&&<p>{t('The online service was unavailable. This result comes from the local leaf model.','অনলাইন সেবা পাওয়া যায়নি। এই ফলটি স্থানীয় পাতার মডেল থেকে এসেছে।')}</p>}
  <h2>{blightPattern?t('Blight-like pattern · cause uncertain','ধসা রোগের মতো লক্ষণ · কারণ অনিশ্চিত'):result.classification.abstained?t('Unable to classify reliably','নির্ভরযোগ্যভাবে শ্রেণিবিন্যাস করা যায়নি'):`${t('Possible','সম্ভাব্য')}: ${conditionName(result.classification.top_label)}`}</h2>
  <p>{reasons[result.classification.rejection_reason||'']||t('Screening support only. Ask a qualified agronomist to review symptoms.','এটি প্রাথমিক সহায়তা। কৃষিবিদের পরামর্শ নিন।')}</p>
  {!classification.abstained&&classification.score!=null&&<p>{t('Uncalibrated model score','অক্যালিব্রেটেড মডেল স্কোর')}: {(classification.score*100).toFixed(1)}% · {t('Not diagnostic certainty','নিশ্চিত রোগ নির্ণয় নয়')}</p>}
   <FarmerActionCard result={result} locale={locale}/>
   {chatButton}
  {result.quality_flags.map(flag=><span className="badge amber" key={flag}>{flag.replaceAll('_',' ')}</span>)}
  {cropOptions.length===0&&result.classification.alternatives.length>0&&<details><summary>{t('Raw model alternatives','মডেলের বিকল্প স্কোর')}</summary>{result.classification.alternatives.map(a=><p key={a.label}>{a.label.split('___')[0].replaceAll('_',' ')} · {conditionName(a.label)}: {(a.score*100).toFixed(1)}%</p>)}</details>}
  {classification.abstained&&cropOptions.length>0&&<details>
   <summary>{t('Model scores for the selected crop','নির্বাচিত ফসলের মডেল স্কোর')}</summary>
   <p>{t('These scores are for comparison only. Compare symptoms in the field or ask an extension officer before acting on a disease label.','এগুলো শুধু তুলনার জন্য। রোগের নাম দেখে ব্যবস্থা নেওয়ার আগে লক্ষণ মিলিয়ে দেখুন অথবা কৃষি কর্মকর্তার পরামর্শ নিন।')}</p>
   {cropOptions.map(option=><p key={option.label}>{conditionName(option.label)} · {(option.score*100).toFixed(1)}%</p>)}
  </details>}
  {guide&&<div className="stack">
   <h3>{t('What to check and do next','এরপর কী দেখবেন ও কী করবেন')}</h3>
   {healthy&&<p>{t('The leaf most closely matches the healthy reference. Rescan another affected leaf if symptoms persist.','?????? ????? ?????? ????? ??????? ???? ??????? ????? ????? ?????? ???????? ????? ??? ??????? ?????')}</p>}
   {!healthy&&<div lang="en">
    <p>{guidance?.[0]??guide.inspect}</p>
    <p>{guidance?.[1]??guide.action}</p>
   </div>}
   {visibleChecks.length>0&&<div className="stack">
    <h4>{t('Compare these symptoms on the plant','গাছে এই লক্ষণগুলো মিলিয়ে দেখুন')}</h4>
    <p>{t('Use these checks to decide what to photograph or show an adviser. The cause is still uncertain.','কী ছবি তুলবেন বা কৃষি কর্মকর্তাকে কী দেখাবেন, তা ঠিক করতে লক্ষণগুলো মিলিয়ে দেখুন। কারণ এখনো অনিশ্চিত।')}</p>
    {visibleChecks.map(label=><div key={label} lang="en">
     <strong>{conditionName(label)}</strong>
     <p>{guide.conditions[label][0]}</p>
     <p>{guide.conditions[label][1]}</p>
    </div>)}
   </div>}
   {classification.abstained&&<details>
    <summary>{t('Compare symptoms covered by this model','মডেলের পরিচিত লক্ষণগুলোর সঙ্গে মিলিয়ে দেখুন')}</summary>
    <div lang="en">
     <p>These are field checks. The photo did not identify a specific condition.</p>
     {Object.entries(guide.conditions).filter(([label])=>!visibleChecks.includes(label)).map(([label,[signs,action]])=><div key={label}>
      <h4>{conditionName(label)}</h4>
      <p>{signs}</p>
      <p>{action}</p>
     </div>)}
    </div>
   </details>}
   <a href={guide.source} target="_blank" rel="noreferrer">{t('Crop health reference','ফসলের স্বাস্থ্য নির্দেশিকা')}</a>
  </div>}
  <h4>{t('Next steps','পরবর্তী করণীয়')}</h4>{result.advice.map(advice=><div className="advice" key={advice}><CheckCircle2 size={16}/><span>{advice}</span></div>)}
  {potatoChecks}
  <div className="model-evidence"><small>{t('MODEL EVIDENCE','মডেলের তথ্য')}</small><strong>{result.model.version}</strong><p>{t('Not field-validated','মাঠ পর্যায়ে যাচাই করা হয়নি')} · {result.model.available?t('Verified artifact installed','যাচাইকৃত মডেল ইনস্টল আছে'):t('Artifact unavailable','মডেল অনুপলব্ধ')}</p>{result.model.source_url&&<a href={result.model.source_url} target="_blank" rel="noreferrer">{t('Upstream model & limitations','মূল মডেল ও সীমাবদ্ধতা')}</a>}<p>{result.disclaimer}</p></div>
 </section>;
}
export function CaseList({cases,locale}:{cases:Case[];locale:Locale}){
 const {data:capabilities}=useDoctorCapabilities();
 return cases.length?<div className="table-wrap"><table><thead><tr><th>{locale==='bn'?'ফসল ও জমি':'Crop & plot'}</th><th>{locale==='bn'?'ফলাফল':'Result'}</th><th>Model</th><th>{locale==='bn'?'সময়':'Bangladesh time'}</th><th/></tr></thead><tbody>{cases.map(c=><tr key={c.id}><td><Leaf size={16}/> {cropName(c.crop||'tomato',capabilities,locale)}<small>{c.plot_name||c.plot_id}</small></td><td>{c.classification.abstained?(locale==='bn'?'অনিশ্চিত':'Uncertain'):conditionName(c.classification.top_label)}</td><td>{c.model.version}</td><td>{formatTime(c.created_at,locale)}</td><td><Link className="text-link" href={`/${locale}/agrodoctor/${c.id}`}>{locale==='bn'?'খুলুন':'Open'}</Link></td></tr>)}</tbody></table></div>:<p>{locale==='bn'?'এই জমির কোনো পর্যবেক্ষণ নেই।':'No observations for this plot yet.'}</p>;
}
export function CasePagination({total,shown,hasMore,pending,onLoadMore}:{total:number;shown:number;hasMore:boolean;pending:boolean;onLoadMore:()=>void}){
 return <><p className="helper">Showing {shown} of {total} saved screenings for this plot.</p>{hasMore&&<button className="btn secondary full" disabled={pending} onClick={onLoadMore}>{pending?'Loading…':'Load older screenings'}</button>}</>;
}
export function CaseDetail({id,perform,locale}:{id:string;perform:Perform;locale:Locale}){
 const {data,error,isPending}=useQuery({queryKey:['case',id],queryFn:()=>request<Case>(`/doctor/cases/${id}`)});
 const [note,setNote]=useState('');const [imgUrl,setImgUrl]=useState('');const [imgError,setImgError]=useState('');
 useEffect(()=>{
  const controller=new AbortController();let url='';let disposed=false;
  async function load(){try{
   const response=await fetch(`${API}/doctor/cases/${id}/image`,{headers:{Authorization:`Bearer ${getSessionToken()}`},signal:controller.signal});
   if(!response.ok)throw new Error(response.status===410?'Photo no longer available. Case metadata is preserved.':'Photo could not be loaded.');
   const blob=await response.blob();if(disposed)return;url=URL.createObjectURL(blob);setImgUrl(url);
  }catch(e){if(!disposed&&!controller.signal.aborted)setImgError((e as Error).message)}}
  void load();return()=>{disposed=true;controller.abort();if(url)URL.revokeObjectURL(url)};
 },[id]);
 if(isPending)return <section className="panel" role="status">Loading case…</section>;
 if(error)return <section className="panel error" role="alert">{error.message}</section>;
 return <div className="two-grid"><DoctorResult result={data} locale={locale} imgUrl={imgUrl} imgError={imgError}/><section className="panel"><h2>{locale==='bn'?'পর্যবেক্ষণের নোট':'Observation notes'}</h2><p>{data.symptoms||'No symptoms recorded.'}</p><label>{locale==='bn'?'নতুন নোট':'New note'}<textarea maxLength={2000} value={note} onChange={e=>setNote(e.target.value)}/></label><button className="btn primary" disabled={!note.trim()} onClick={()=>void perform(async()=>{await request(`/doctor/cases/${id}/feedback`,{method:'POST',body:JSON.stringify({note:note.trim(),request_review:false})});setNote('')},'Note saved')}>Save note</button><button className="btn secondary" disabled={!note.trim()} onClick={()=>void perform(async()=>{await request(`/doctor/cases/${id}/feedback`,{method:'POST',body:JSON.stringify({note:note.trim(),request_review:true})});setNote('')},'Review request recorded locally')}>Record review request</button><p className="helper">Private notes only. No advisor has been contacted.</p>{data.feedback?.map(feedback=><div className="timeline-row" key={feedback.id}><div><strong>{feedback.request_review?'Local review request':'Note'}</strong><p>{feedback.note}</p><small>{formatTime(feedback.created_at,locale)}</small></div></div>)}<div className="row wrap"><button className="btn secondary" onClick={()=>void perform(()=>download(`/doctor/cases/${id}/report`,'agrodoctor-case.csv'),'Report downloaded')}><Download size={16}/>Export CSV</button><button className="btn secondary" disabled={!imgUrl} onClick={()=>void perform(()=>download(`/doctor/cases/${id}/image`,`${data.crop||'tomato'}-photo.jpg`),'Photo downloaded')}><Download size={16}/>Download photo</button><button className="btn danger" onClick={()=>void perform(async()=>{await request(`/doctor/cases/${id}`,{method:'DELETE'});location.href=`/${locale}/agrodoctor`},'Case deleted')}><Trash2 size={16}/>Delete observation</button></div></section></div>;
}
