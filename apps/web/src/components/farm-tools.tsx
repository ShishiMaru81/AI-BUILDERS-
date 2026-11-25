'use client';

import {useState, useSyncExternalStore} from 'react';
import Link from 'next/link';
import {useQuery, useQueryClient} from '@tanstack/react-query';
import {getSessionToken, request} from '@/lib/api';
import type {Action, Plot} from '@/lib/types';
import {saveNotebook} from '@/lib/farm-notebook';
import {FarmLedger} from './farm-ledger';
import {StorageTracker} from './storage-tracker';
import {CommunityReports} from './community-reports';
import {day, fields, number, stages, type FarmToolData, type Locale, type Localize, type Write} from './farm-tools-data';

const tabs = [
  ['calendar','Calendar & alerts','পঞ্জিকা ও সতর্কতা'], ['ledger','Cash ledger','আয়-ব্যয়'],
  ['storage','Storage','সংরক্ষণ'], ['community','Community map','এলাকার মানচিত্র'], ['offline','Offline notebook','অফলাইন খাতা'],
] as const;
function subscribeHash(callback:()=>void) {
  window.addEventListener('hashchange',callback);
  return ()=>window.removeEventListener('hashchange',callback);
}
function hash() {return window.location.hash.slice(1);}

type View = {
  data:FarmToolData; base:string; locale:Locale; t:Localize; write:Write; busy:boolean;
};

function Calendar({data, base, locale, t, write, busy}: View) {
  const today=data.today;
  const calendar=data.calendar;
  return <>
    <section className="panel">
      <h2>{t('Weekly crop advisory','সাপ্তাহিক ফসল পরামর্শ')}</h2>
      <p>{t('Week of','সপ্তাহ শুরু')} {day(calendar.week_start,locale)}{calendar.district?' · '+calendar.district:''}
        {calendar.planting_week!==null&&` · ${t('Growing week','চাষের সপ্তাহ')} ${number(calendar.planting_week,locale)}`}</p>
      {calendar.tasks.length ? <ul className="farm-tool-list">{calendar.tasks.map(task=><li key={task.date}>
        <div><strong>{task[locale]}</strong><small>{day(task.date,locale)}</small></div>
        <button className="text-link" disabled={busy||data.reminders.some(row=>row.due_on===task.date&&row.label===task[locale].slice(0,100))}
          onClick={()=>void write(base+'/reminders','POST',{label:task[locale].slice(0,100),due_on:task.date})}>{t('Remind me','মনে করিয়ে দিন')}</button>
      </li>)}</ul> : <p>{t('Stage-based guidance is available for potato and tomato. Confirm the crop stage below.',
        'আলু ও টমেটোর বৃদ্ধির পর্যায়ভিত্তিক পরামর্শ পাওয়া যায়। নিচে ফসলের পর্যায় নিশ্চিত করুন।')}</p>}
      {calendar.source_url&&<a href={calendar.source_url} target="_blank" rel="noreferrer">
        {t('BAMIS crop weather calendar','বামিস ফসল আবহাওয়া পঞ্জিকা')}{calendar.region&&' · '+calendar.region}
      </a>}
      <form key={`${data.planting_date}:${calendar.stage}`} onSubmit={e=>{
        e.preventDefault();
        const values=fields(e.currentTarget);
        void write(base+'/planting','PATCH',{...values,date:values.date || null});
      }}>
        <div className="form-grid">
          <label>{t('Planting date (optional)','রোপণের তারিখ (ঐচ্ছিক)')}<input name="date" type="date" defaultValue={data.planting_date||''} max={today}/></label>
          <label>{t('Current crop stage','ফসলের বর্তমান পর্যায়')}<select name="stage" defaultValue={calendar.stage||'Vegetative'}>
            {stages.map(([en,bn])=><option key={en} value={en}>{t(en,bn)}</option>)}
          </select></label>
        </div>
        <button className="btn secondary" disabled={busy}>{t('Update growing details','চাষের তথ্য হালনাগাদ করুন')}</button>
      </form>
    </section>
    <section className="panel">
      <h2>{t('Alerts and reminders','সতর্কতা ও মনে করিয়ে দেওয়া')}</h2>
      <p>{t('Alerts use saved live rainfall and recent screenings. Reminders appear here when due.',
        'সংরক্ষিত হালনাগাদ বৃষ্টির পূর্বাভাস ও সাম্প্রতিক পরীক্ষা থেকে সতর্কতা তৈরি হয়। সময় হলে রিমাইন্ডার এখানে দেখাবে।')}</p>
      <ul className="farm-tool-list">
        {data.alerts.map(alert=><li key={alert.id}>
          <div><strong>{alert[locale]}</strong>{alert.source_url&&<small>{alert.detail} mm / {alert.hours} h · <a href={alert.source_url}>{t('Open-Meteo forecast','ওপেন-মিটিও পূর্বাভাস')}</a></small>}</div>
          <button className="text-link" disabled={busy} onClick={()=>void write(base+'/alerts/'+alert.id+'/dismiss','POST')}>{t('Dismiss','সরান')}</button>
        </li>)}
        {[...data.reminders].sort((a,b)=>a.due_on.localeCompare(b.due_on)).map(row=><li key={row.id}>
          <div><strong>{row.label}</strong><small>{day(row.due_on,locale)} · {row.due_on<=today?t('Due','সময় হয়েছে'):t('Upcoming','আসন্ন')}</small></div>
          <button className="text-link" disabled={busy} onClick={()=>void write('/farm-tools/records/farm_reminder/'+row.id,'DELETE')}>{t(row.due_on<=today?'Complete':'Cancel',row.due_on<=today?'সম্পন্ন':'বাতিল')}</button>
        </li>)}
      </ul>
      {!data.alerts.length&&!data.reminders.length&&<p>{t('No alerts or reminders for this plot.','এই জমির কোনো সতর্কতা বা রিমাইন্ডার নেই।')}</p>}
      <form onSubmit={e=>{
        e.preventDefault();
        const form=e.currentTarget;
        void write(base+'/reminders','POST',fields(form)).then(ok=>{if(ok)form.reset();});
      }}>
        <div className="form-grid">
          <label>{t('Reminder','মনে করিয়ে দিন')}<input name="label" required maxLength={100}/></label>
          <label>{t('Due date','নির্ধারিত তারিখ')}<input name="due_on" type="date" required defaultValue={today}/></label>
        </div>
        <button className="btn primary" disabled={busy}>{t('Add reminder','রিমাইন্ডার যোগ করুন')}</button>
      </form>
    </section>
  </>;
}

function OfflineNotebook({data, actions, locale, t}: Pick<View,'data'|'locale'|'t'> & {actions:Action[]}) {
  const [saving,setSaving]=useState(false);
  const [notice,setNotice]=useState('');
  const [error,setError]=useState('');
  return <section className="panel">
    <h2>{t('Save this plot for offline reading','অফলাইনে পড়ার জন্য এই জমির তথ্য রাখুন')}</h2>
    <p>{t('Save a password-protected copy of this plot’s records and advice on this device. Save again when you want the latest version.',
      'এই ডিভাইসে জমির তথ্য ও পরামর্শের পাসওয়ার্ড দেওয়া কপি রাখুন। নতুন তথ্যের জন্য আবার সংরক্ষণ করুন।')}</p>
    <form onSubmit={async e=>{
      e.preventDefault();
      const form=e.currentTarget, passphrase=fields(form).passphrase, token=getSessionToken();
      setError('');setNotice('');setSaving(true);
      try {
        await saveNotebook({locale,title:data.plot_name,groups:[
          {title:t('Crop and stage','ফসল ও পর্যায়'), items:[`${data.calendar.crop} · ${data.calendar.stage}`]},
          {title:t('Calendar and saved actions','পঞ্জিকা ও সংরক্ষিত কাজ'),items:[
            ...data.calendar.tasks.map(task=>day(task.date,locale)+' · '+task[locale]),
            ...actions.filter(action=>action.status==='open').map(action=>action.title+' · '+action.reason),
            ...data.reminders.map(reminder=>day(reminder.due_on,locale)+' · '+reminder.label),
          ]},
          {title:t('Cash ledger','আয়-ব্যয়ের খাতা'),items:data.ledger.map(line=>
            day(line.date,locale)+' · '+line.label+' · '+(line.kind==='expense'?'−':'+')+'৳'+number(line.amount_bdt,locale,2))},
          {title:t('Stored batches','সংরক্ষিত ব্যাচ'),items:data.storage.map(batch=>
            batch.label+' · '+day(batch.stored_on,locale)+' · '+number(batch.remaining_kg,locale)+t(' kg remaining',' কেজি অবশিষ্ট'))},
        ]},passphrase,()=>!!token&&getSessionToken()===token);
        form.reset();
        setNotice(t('Offline copy saved. Open the notebook to read or install it.','অফলাইন কপি সংরক্ষিত। পড়তে বা ইনস্টল করতে খাতাটি খুলুন।'));
      } catch (failure) {
        setError((failure as Error).message);
      } finally {setSaving(false);}
    }}>
      <label>{t('New notebook passphrase (10 or more characters)','খাতার নতুন পাসওয়ার্ড (অন্তত ১০ অক্ষর)')}
        <input name="passphrase" type="password" autoComplete="new-password" minLength={10} maxLength={128} required/>
      </label>
      <div className="row wrap">
        <button className="btn primary" disabled={saving}>{saving?t('Saving…','সংরক্ষণ হচ্ছে…'):t('Save encrypted copy','সুরক্ষিত কপি রাখুন')}</button>
        <a className="btn secondary" href="/offline-farm.html">{t('Open offline notebook','অফলাইন খাতা খুলুন')}</a>
      </div>
      {notice&&<p role="status">{notice}</p>}
      {error&&<p className="error" role="alert">{error}</p>}
    </form>
  </section>;
}

export function FarmTools({locale, plot, userId, actions}: {locale:Locale; plot?:Plot; userId:string; actions:Action[]}) {
  const currentTab=useSyncExternalStore(subscribeHash,hash,()=> '');
  const tab=tabs.some(([id])=>id===currentTab)?currentTab:'calendar';
  const t:Localize=(en,bn)=>locale==='bn'?bn:en;
  const qc=useQueryClient();
  const base='/farm-tools/plots/'+plot?.id;
  const key=['farm-tools',userId,plot?.id];
  const query=useQuery({
    queryKey:key, queryFn:({signal})=>request<FarmToolData>(base,{signal}), enabled:!!plot,
    refetchInterval:60_000,
  });
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const write:Write=async(path,method,body)=>{
    setError('');setBusy(true);
    try {
      await request(path,{method,body:body===undefined?undefined:JSON.stringify(body)});
      const related=path.includes('community')?['farm-community']:path.endsWith('/planting')?['plots']:['farm-break-even'];
      await Promise.all([qc.invalidateQueries({queryKey:key}),qc.invalidateQueries({queryKey:related})]);
      return true;
    } catch (failure) {
      setError((failure as Error).message);
      return false;
    } finally {setBusy(false);}
  };
  if(!plot)return <section className="panel">
    <h2>{t('Set up a crop plot','ফসলের জমি যোগ করুন')}</h2>
    <Link href={`/${locale}/farms`}>{t('Open Farms & plots','খামার ও জমি খুলুন')}</Link>
  </section>;
  if(query.isPending)return <p role="status">{t('Loading plot tools…','জমির কাজ লোড হচ্ছে…')}</p>;
  if(query.isError)return <section className="panel">
    <p className="error" role="alert">{query.error.message}</p>
    <button className="btn secondary" onClick={()=>void query.refetch()}>{t('Retry','আবার চেষ্টা করুন')}</button>
  </section>;
  const props={data:query.data,base,locale,t,write,busy};
  return <div className="farm-tools">
    <nav className="farm-tool-tabs" aria-label={t('Farm tools','খামারের কাজ')}>
      {tabs.map(([id,en,bn])=><a aria-current={tab===id?'page':undefined} href={'#'+id} key={id}>{t(en,bn)}</a>)}
    </nav>
    {error&&<p className="error" role="alert">{error}</p>}
    {tab==='calendar'&&<Calendar {...props}/>}
    {tab==='ledger'&&<FarmLedger {...props}/>}
    {tab==='storage'&&<StorageTracker {...props}/>}
    {tab==='community'&&<CommunityReports {...props} plotId={plot.id}/>}
    {tab==='offline'&&<OfflineNotebook {...props} actions={actions}/>}
  </div>;
}

export function FarmToolsNotice({locale,plotId,userId}: {locale:Locale;plotId:string;userId:string}) {
  const t:Localize=(en,bn)=>locale==='bn'?bn:en;
  const query=useQuery({
    queryKey:['farm-tools',userId,plotId],
    queryFn:({signal})=>request<FarmToolData>('/farm-tools/plots/'+plotId,{signal}),
    refetchInterval:60_000,
  });
  const data=query.data;
  if(!data)return null;
  const due=data.reminders.filter(row=>row.due_on<=data.today).length + data.alerts.length;
  return <section className="panel row between wrap">
    <div><h3>{t('Calendar and alerts','পঞ্জিকা ও সতর্কতা')}</h3>
      <p>{due?number(due,locale)+t(' items need your attention','টি কাজে নজর দিন'):t('No alerts or reminders due','নির্ধারিত কোনো সতর্কতা বা রিমাইন্ডার নেই')}</p></div>
    <Link className="btn secondary" href={`/${locale}/farm-tools`}>{t('Open farm tools','খামারের কাজ খুলুন')}</Link>
  </section>;
}
