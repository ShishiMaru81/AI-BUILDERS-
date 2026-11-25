'use client';

import {useState} from 'react';
import {day, fields, methods, movements, number, type Batch, type FarmToolData, type Locale, type Localize, type Write} from './farm-tools-data';

type Tools = {locale:Locale; t:Localize; write:Write; busy:boolean};
function BatchCard({batch, today, locale, t, write, busy}: Tools & {batch:Batch; today:string}) {
  const [kind,setKind]=useState('inspection');
  const url='/farm-tools/storage/'+batch.id+'/events';
  const kg=(value:number|string)=>number(value,locale)+t(' kg',' কেজি');
  return <section className="panel">
    <h3>{batch.label}</h3>
    <p>{t('Harvested','ফসল তোলা হয়েছে')} {day(batch.harvested_on,locale)} · {t('Stored','সংরক্ষণ শুরু')} {day(batch.stored_on,locale)}</p>
    <p>{methods.map(([id,en,bn])=>id===batch.method?t(en,bn):null)}</p>
    <dl className="farm-tool-totals">
      <div><dt>{t('Initially stored','শুরুতে সংরক্ষিত')}</dt><dd>{kg(batch.quantity_kg)}</dd></div>
      <div><dt>{t('Remaining','অবশিষ্ট')}</dt><dd>{kg(batch.remaining_kg)}</dd></div>
      <div><dt>{t('Loss','ক্ষতি')}</dt><dd>{kg(batch.loss_kg)} ({number(batch.loss_pct,locale,1)}%)</dd></div>
    </dl>
    <details>
      <summary>{t('Log a storage event','সংরক্ষণের ঘটনা লিখুন')}</summary>
      <form onSubmit={e=>{
        e.preventDefault();
        const form=e.currentTarget, body=fields(form);
        void write(url,'POST',{...body,kind,quantity_kg:kind==='inspection'?null:body.quantity_kg})
          .then(ok=>{if(ok)form.reset();});
      }}>
        <div className="form-grid">
          <label>{t('Event type','ঘটনার ধরন')}<select value={kind} onChange={e=>setKind(e.target.value)}>
            {movements.map(([id,en,bn])=><option key={id} value={id}>{t(en,bn)}</option>)}
          </select></label>
          <label>{t('Observation or reason','পর্যবেক্ষণ বা কারণ')}<input name="label" required maxLength={100}/></label>
          <label>{t('Event date','ঘটনার তারিখ')}<input name="date" type="date" required min={batch.stored_on} max={today} defaultValue={today}/></label>
          {kind!=='inspection'&&<label>{t('Weight (kg)','ওজন (কেজি)')}<input name="quantity_kg" required type="number" min=".001" max={batch.remaining_kg} step=".001"/></label>}
        </div>
        <button className="btn secondary" disabled={busy}>{t('Save event','ঘটনা সংরক্ষণ করুন')}</button>
      </form>
    </details>
    {!!batch.events.length&&<ul className="farm-tool-list">{[...batch.events].reverse().map(event=><li key={event.id}>
      <span><strong>{event.label}</strong><small>{day(event.date,locale)} · {movements.map(([id,en,bn])=>id===event.kind?t(en,bn):null)} {event.quantity_kg&&kg(event.quantity_kg)}</small></span>
      <button type="button" className="text-link" disabled={busy} onClick={()=>{
        if(window.confirm(t('Delete this storage event?','এই ঘটনা মুছবেন?')))void write(url+'/'+event.id,'DELETE');
      }}>{t('Delete event','ঘটনা মুছুন')}</button>
    </li>)}</ul>}
    <button type="button" className="text-link" disabled={busy} onClick={()=>{
      if(window.confirm(t('Delete this batch and its events?','এই ব্যাচ ও সব ঘটনা মুছবেন?')))void write('/farm-tools/records/storage_batch/'+batch.id,'DELETE');
    }}>{t('Delete batch','ব্যাচ মুছুন')}</button>
  </section>;
}

export function StorageTracker({data, base, locale, t, write, busy}: Tools & {data:FarmToolData; base:string}) {
  return <>
    <section className="panel">
      <h2>{t('Post-harvest storage','ফসল তোলার পর সংরক্ষণ')}</h2>
      <p>{t('Track remaining stock and losses from your recorded weights. Add sales to the cash ledger separately.',
        'লিখিত ওজন থেকে অবশিষ্ট মজুত ও ক্ষতি দেখুন। বিক্রির টাকা আয়-ব্যয়ের খাতায় লিখুন।')}</p>
      <form onSubmit={e=>{
        e.preventDefault();
        const form=e.currentTarget;
        void write(base+'/storage','POST',fields(form)).then(ok=>{if(ok)form.reset();});
      }}>
        <div className="form-grid">
          <label>{t('Batch name','ব্যাচের নাম')}<input name="label" required maxLength={100}/></label>
          <label>{t('Storage method','সংরক্ষণের পদ্ধতি')}<select name="method">
            {methods.map(([id,en,bn])=><option key={id} value={id}>{t(en,bn)}</option>)}
          </select></label>
          <label>{t('Harvest date','ফসল তোলার তারিখ')}<input name="harvested_on" type="date" required max={data.today} defaultValue={data.today}/></label>
          <label>{t('Storage date','সংরক্ষণের তারিখ')}<input name="stored_on" type="date" required max={data.today} defaultValue={data.today}/></label>
          <label>{t('Stored weight (kg)','সংরক্ষিত ওজন (কেজি)')}<input name="quantity_kg" type="number" min=".001" max="1000000" step=".001" required/></label>
        </div>
        <button className="btn primary" disabled={busy}>{t('Save batch','ব্যাচ সংরক্ষণ করুন')}</button>
      </form>
    </section>
    {data.storage.map(batch=><BatchCard key={batch.id} {...{batch,locale,t,write,busy}} today={data.today}/>)}
  </>;
}
