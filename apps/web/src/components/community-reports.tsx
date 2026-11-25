'use client';

import {useState} from 'react';
import Link from 'next/link';
import {useQuery} from '@tanstack/react-query';
import {request} from '@/lib/api';
import type {PaginatedCases} from '@/lib/types';
import {day, type FarmToolData, type Locale, type Localize, type Write} from './farm-tools-data';

type District = {id:string; en:string; bn:string; band:string|null};
type Reports = {start:string; end:string; districts:District[]};

export function CommunityReports({data, plotId, base, locale, t, write, busy}: {
  data:FarmToolData; plotId:string; base:string; locale:Locale; t:Localize; write:Write; busy:boolean;
}) {
  const [crop,setCrop]=useState(data.calendar.crop==='potato'?'potato':'tomato');
  const [selected,setSelected]=useState(data.calendar.district || '');
  const [caseId,setCaseId]=useState('');
  const [consent,setConsent]=useState(false);
  const reports=useQuery({
    queryKey:['farm-community',crop],
    queryFn:({signal})=>request<Reports>('/farm-tools/community?crop='+crop,{signal}),
  });
  const shapes=useQuery({
    queryKey:['district-boundaries'],
    queryFn:async({signal})=>{
      const result=await fetch('/bangladesh-district-paths.json',{signal});
      if(!result.ok)throw new Error('District geometry unavailable');
      return await result.json() as Record<string,string>;
    },
    staleTime:Infinity,
  });
  const cases=useQuery({
    queryKey:['farm-share-cases',plotId],
    queryFn:({signal})=>request<PaginatedCases>(`/doctor/cases?plot_id=${encodeURIComponent(plotId)}&offset=0&limit=50`,{signal}),
    enabled:data.sharing_allowed,
  });
  const list=reports.data?.districts || [];
  const district=list.find(item=>item.id===selected);
  const active=list.filter(item=>item.band);
  const eligible=cases.data?.items.filter(item=>!item.meta.is_simulated && !data.shared_case_ids.includes(item.id)) || [];
  return <>
    <section className="panel community-reports">
      <h2>{t('Community crop reports','এলাকার ফসলের প্রতিবেদন')}</h2>
      <p>{t('See districts with reports from at least three farmers. These are shared screening observations.',
        'অন্তত তিনজন কৃষকের প্রতিবেদন আছে এমন জেলা দেখুন। এগুলো কৃষকের শেয়ার করা পরীক্ষার পর্যবেক্ষণ।')}</p>
      <div className="form-grid">
        <label>{t('Crop','ফসল')}<select value={crop} onChange={e=>setCrop(e.target.value)}>
          <option value="tomato">{t('Tomato','টমেটো')}</option><option value="potato">{t('Potato','আলু')}</option>
        </select></label>
        <label>{t('District','জেলা')}<select value={selected} onChange={e=>setSelected(e.target.value)}>
          <option value="">{t('All districts','সব জেলা')}</option>
          {list.map(item=><option key={item.id} value={item.id}>{item[locale]}</option>)}
        </select></label>
      </div>
      {reports.isPending&&<p role="status">{t('Loading reports…','প্রতিবেদন লোড হচ্ছে…')}</p>}
      {reports.isError&&<p role="alert">{t('Reports are unavailable.','প্রতিবেদন পাওয়া যাচ্ছে না।')} <button className="text-link" onClick={()=>void reports.refetch()}>{t('Retry','আবার চেষ্টা করুন')}</button></p>}
      {reports.data&&<p>{day(reports.data.start,locale)} – {day(reports.data.end,locale)}</p>}
      <div className="farm-tool-map">
        {shapes.data&&<svg viewBox="0 0 420 365" role="img" aria-label={t('Bangladesh district map, with reported districts highlighted','বাংলাদেশের জেলা মানচিত্রে প্রতিবেদন থাকা জেলা চিহ্নিত')}>
          {list.map(item=><path key={item.id} d={shapes.data[item.id]} fillRule="evenodd"
            className={`${item.band?'reported':''} ${item.id===selected?'selected':''}`}
            onClick={()=>setSelected(item.id)}>
            <title>{item[locale]}{item.band?' · '+item.band:''}</title>
          </path>)}
        </svg>}
        {shapes.isError&&<p>{t('Map outline unavailable. Use the district list.','মানচিত্র পাওয়া যাচ্ছে না। জেলার তালিকা ব্যবহার করুন।')}</p>}
        {reports.isSuccess&&<div aria-live="polite">
          {district ? <p><strong>{district[locale]}</strong>{' · '}{district.band
            ? district.band + t(' reporting farmers',' জন প্রতিবেদক কৃষক')
            : t('Below the publication threshold','প্রকাশের জন্য যথেষ্ট প্রতিবেদন নেই')}</p>
            : active.length ? <ul>{active.map(item=><li key={item.id}><button className="text-link" onClick={()=>setSelected(item.id)}>{item[locale]} · {item.band}</button></li>)}</ul>
              : <p>{t('No districts have enough reports to display for this crop.','এই ফসলের জন্য কোনো জেলায় প্রদর্শনের মতো পর্যাপ্ত প্রতিবেদন নেই।')}</p>}
        </div>}
      </div>
      <small>{t('Boundaries: BBS and OCHA ROAP via geoBoundaries, simplified for display.','সীমানা: বিবিএস ও ওসিএইচএ, geoBoundaries থেকে সরলীকৃত।')}{' '}
        <a href="https://www.geoboundaries.org/api/current/gbOpen/BGD/ADM2/" target="_blank" rel="noreferrer">{t('Source and license','উৎস ও লাইসেন্স')}</a>
      </small>
    </section>
    <section className="panel">
      <h3>{t('Share a screening observation','পরীক্ষার পর্যবেক্ষণ শেয়ার করুন')}</h3>
      {data.sharing_allowed ? <>
        <form onSubmit={event=>{
          event.preventDefault();
          void write(base+'/community','POST',{case_id:caseId,consent:true}).then(ok=>{if(ok){setConsent(false);setCaseId('');}});
        }}>
          <label>{t('Saved screening','সংরক্ষিত পরীক্ষা')}
            <select value={caseId} onChange={e=>setCaseId(e.target.value)} required>
              <option value="">{t('Choose a screening','পরীক্ষা বাছুন')}</option>
              {eligible.map(item=><option key={item.id} value={item.id}>
                {day(item.created_at.slice(0,10),locale)} · {item.classification.top_label || t('Screening','পরীক্ষা')}
              </option>)}
            </select>
          </label>
          <label className="checkbox-label"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)} required/>
            {t('Count my crop observation in an anonymous district total. My photos and farm details stay private.',
              'আমার ফসলের পর্যবেক্ষণ নাম ছাড়া জেলার মোট হিসাবে যোগ করুন। ছবি ও খামারের তথ্য ব্যক্তিগত থাকবে।')}</label>
          <button className="btn primary" disabled={busy||!consent||!caseId}>{t('Share observation','পর্যবেক্ষণ শেয়ার করুন')}</button>
        </form>
        {cases.isError&&<p role="alert">{t('Could not load screenings.','পরীক্ষার তালিকা লোড হয়নি।')} <button className="text-link" onClick={()=>void cases.refetch()}>{t('Retry','আবার চেষ্টা করুন')}</button></p>}
        {cases.isSuccess&&!eligible.length&&<Link href={`/${locale}/agrodoctor`}>{t('Save a live screening in AgroDoctor','এগ্রোডক্টরে একটি হালনাগাদ পরীক্ষা সংরক্ষণ করুন')}</Link>}
      </> : <p>{t('Sharing requires a non-demo account and a recognized Bangladesh district.','শেয়ার করতে নিবন্ধিত অ্যাকাউন্ট ও বাংলাদেশের পরিচিত জেলা লাগবে।')}</p>}
      {!!data.shared_case_ids.length&&<ul className="farm-tool-list">{data.shared_case_ids.map(id=><li key={id}>
        <Link href={`/${locale}/agrodoctor/${id}`}>{t('Open shared screening','শেয়ার করা পরীক্ষা খুলুন')} · {id.slice(0,6)}</Link>
        <button type="button" className="text-link" disabled={busy} onClick={()=>void write('/farm-tools/community/'+id,'DELETE')}>
          {t('Withdraw','শেয়ার প্রত্যাহার করুন')}
        </button>
      </li>)}</ul>}
    </section>
  </>;
}
