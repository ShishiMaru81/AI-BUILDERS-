'use client';

import {useState, type CSSProperties} from 'react';
import {useQuery} from '@tanstack/react-query';
import {ArrowUpRight, CheckCircle2, CloudRain, MapPin} from 'lucide-react';
import {Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import {formatTime, request} from '@/lib/api';
import type {Farm, Plot, Weather} from '@/lib/types';
import {FarmLocationEditor} from './location-picker';
import styles from './flood-motion.module.css';

type Mode = 'LIVE' | 'DEMO';

function RainScene({hasRain}: {hasRain: boolean}) {
  return <div className={styles.scene} aria-hidden="true" data-testid="rain-outlook-scene">
    <span className={styles.hills}/>
    <span className={styles.fields}/>
    <span className={styles.cloud}/>
    {hasRain&&<span className={styles.rain} data-testid="rain-outlook-streaks"/>}
  </div>;
}

export function FloodOutlook({plot, farm, busy, perform, locale}: {
  plot: Plot; farm: Farm; busy: boolean; locale: 'en'|'bn';
  perform: (fn:()=>Promise<unknown>, message?:string)=>Promise<void>;
}) {
  const t=(en:string,bn:string)=>locale==='bn'?bn:en;
  const [horizon,setHorizon]=useState(48);
  const [source,setSource]=useState<Mode>();
  const hasLocation=Boolean(farm.location_consent && farm.latitude!=null && farm.longitude!=null);
  const mode:Mode=hasLocation?(source??'LIVE'):'DEMO';
  const forecast=useQuery({
    queryKey:['weather',plot.id,farm.id,farm.latitude,farm.longitude,horizon,mode,plot.low_lying],
    queryFn:({signal})=>request<Weather>(`/flood/plots/${plot.id}/outlook?horizon_hours=${horizon}&mode=${mode}`,{signal}),
    staleTime:300000,retry:false,
  });
  const data=forecast.isError?undefined:forecast.data;
  const expired=data?.is_expired||data?.meta.freshness==='expired';
  const hourly=data?.hourly.slice(0,horizon);
  const windowStart=data?.valid_from??hourly?.[0]?.time;
  const lastSlot=hourly?.at(-1)?.time;
  const windowEnd=data?.horizon_valid_until??(lastSlot?new Date(new Date(lastSlot).getTime()+3600000).toISOString():undefined);
  const forecastKey=`${mode}:${horizon}:${data?.meta.retrieved_at ?? ''}`;
  const clock=new Intl.DateTimeFormat(locale==='bn'?'bn-BD':'en-BD',{
    weekday:'short',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Dhaka',
  });
  return <>
    <div className="row between filters">
      <div className={`segmented ${styles.windows}`} role="group" aria-label={t('Forecast window','পূর্বাভাসের সময়সীমা')}
        style={{'--window':horizon/24-1} as CSSProperties}>{[24,48,72].map(h=>
        <button key={h} type="button" aria-pressed={horizon===h} onClick={()=>setHorizon(h)}>
          {h} {t('hours','ঘণ্টা')}
        </button>)}</div>
      <label className="inline-label">{t('Source','উৎস')}
        <select aria-label="Weather data mode" value={mode} onChange={e=>setSource(e.target.value as Mode)}>
          <option value="DEMO">{t('Simulated rainfall','নমুনা বৃষ্টিপাত')}</option>
          <option value="LIVE" disabled={!hasLocation}>{t('Live forecast','হালনাগাদ পূর্বাভাস')}</option>
        </select>
      </label>
    </div>
    <div className="flood-grid">
      <section className="panel">
        <div className="section-heading"><div><span className="eyebrow">{t('PLOT CONTEXT','জমির অবস্থান')}</span>
          <h2>{farm.location_name||farm.district||farm.name}</h2></div><MapPin size={22}/></div>
        {!hasLocation&&<p>{t('Save the farm location below to enable a live forecast.','হালনাগাদ পূর্বাভাস পেতে নিচে খামারের অবস্থান সংরক্ষণ করুন।')}</p>}
        <FarmLocationEditor key={`${farm.id}:${farm.latitude}:${farm.longitude}`} farm={farm} perform={perform} locale={locale} onSaved={()=>setSource('LIVE')}/>
        <label className="checkbox-label"><input type="checkbox" checked={Boolean(plot.low_lying)} disabled={busy}
          onChange={e=>{const low_lying=e.target.checked;void perform(()=>request(`/flood/plots/${plot.id}/vulnerability`,{
            method:'POST',body:JSON.stringify({low_lying}),
          }),t('Plot waterlogging history updated','জমির জলাবদ্ধতার তথ্য সংরক্ষিত হয়েছে'))}}/>
          {t('My plot is low-lying or has prior waterlogging','আমার জমি নিচু বা আগে জলাবদ্ধতা হয়েছে')}
        </label>
      </section>
      <section className="panel rain-summary" aria-live="polite">
        <span className="icon-box blue rain-icon" data-refreshing={forecast.isFetching} aria-hidden="true"><CloudRain size={27}/></span>
        <span className="eyebrow">{locale==='bn'?`${horizon} ঘণ্টার বৃষ্টির পূর্বাভাস`:`${horizon}-HOUR RAIN OUTLOOK`}</span>
        {forecast.isError&&<div className="error" role="alert">
          <p>{mode==='LIVE'?t('Live weather unavailable.','হালনাগাদ আবহাওয়া পাওয়া যাচ্ছে না।'):t('Sample outlook unavailable.','নমুনা পূর্বাভাস পাওয়া যাচ্ছে না।')}</p>
          <p>{forecast.error.message}</p>
        </div>}
        {forecast.isFetching&&<p role="status">{t('Loading rainfall outlook…','বৃষ্টির পূর্বাভাস লোড হচ্ছে…')}</p>}
        {data&&<>
          <div className="rain-total ui-reveal" key={forecastKey}>{data.total_mm}<small>{t('mm','মিমি')}</small></div>
          <span className="badge amber">{expired?t('Forecast expired','পূর্বাভাসের মেয়াদ শেষ'):
            data.level==='prepare'?t('Review rain preparations','বৃষ্টির প্রস্তুতি পর্যালোচনা করুন'):t('Monitor conditions','পরিস্থিতি পর্যবেক্ষণ করুন')}</span>
          <div className="source"><span className={`badge ${data.meta.is_simulated?'amber':'green'}`}>
            {data.meta.is_simulated?t('Simulated scenario','নমুনা পরিস্থিতি'):t('Live forecast','হালনাগাদ পূর্বাভাস')}</span>
            <span>{data.meta.source_name}</span>
            {data.meta.freshness==='stale'&&<span className="badge amber">{t('Older forecast','পুরোনো পূর্বাভাস')}</span>}
          </div>
          {!expired&&<RainScene key={forecastKey} hasRain={data.total_mm>0}/>}
          {windowStart&&windowEnd&&<p>{formatTime(windowStart,locale)} – {formatTime(windowEnd,locale)}</p>}
          {data.meta.retrieved_at&&<small className="helper">{t('Retrieved','তথ্য সংগ্রহ')} {formatTime(data.meta.retrieved_at,locale)}</small>}
          <h3>{t('Preparedness, explained.','প্রস্তুতির কারণ')}</h3>
          <p>{t(`The preparation threshold for this plot is ${data.threshold_mm} mm over ${data.horizon_hours} hours. It is an illustrative rainfall rule.`,
            `এই জমিতে ${data.horizon_hours} ঘণ্টায় ${data.threshold_mm} মিমি বৃষ্টির সীমা ধরে প্রস্তুতির পরামর্শ দেখানো হয়। এটি একটি উদাহরণভিত্তিক নিয়ম।`)}</p>
        </>}
        <button type="button" className="btn secondary" disabled={forecast.isFetching} onClick={()=>void forecast.refetch()}>
          {forecast.isError?t('Retry forecast','আবার চেষ্টা করুন'):t('Refresh outlook','পূর্বাভাস হালনাগাদ করুন')}
        </button>
      </section>
    </div>
    {hourly&&hourly.length>0&&<section className="panel rain-result-chart" key={forecastKey}>
      <div className="section-heading"><h2>{t('Hourly precipitation','ঘণ্টাভিত্তিক বৃষ্টিপাত')}</h2></div>
      <div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={hourly}>
        <CartesianGrid vertical={false} stroke="var(--line)"/><XAxis dataKey="time" minTickGap={48} axisLine={false} tickLine={false} tickFormatter={value=>clock.format(new Date(value))}/>
        <YAxis unit=" mm" width={55} axisLine={false} tickLine={false}/>
        <Tooltip labelFormatter={value=>formatTime(String(value),locale)}/>
        <Area type="linear" dataKey="rain_mm" name={t('Rainfall','বৃষ্টিপাত')} unit=" mm" stroke="#168b5d" fill="#168b5d" fillOpacity={0.22} isAnimationActive={false}/>
      </AreaChart></ResponsiveContainer></div>
    </section>}
    <div className="two-grid">
      {data&&!expired&&<section className="panel"><h3>{t('Practical preparation','প্রস্তুতি ও করণীয়')}</h3>
        {(data.level==='prepare'?[t('Inspect drainage and clear blocked channels.','পানি নিষ্কাশনের পথ দেখুন এবং বাধা সরিয়ে দিন।'),
          t('Protect seedlings and stored produce.','চারা ও সংরক্ষিত ফসল সুরক্ষিত রাখুন।')]:
          [t('Monitor the forecast and check the plot for standing water.','পূর্বাভাস দেখুন এবং জমিতে পানি জমেছে কি না খেয়াল করুন।')]).map(note=>
          <div className="advice" key={note}><CheckCircle2 size={17}/>{note}</div>)}
        <p className="helper">{t(data.disclaimer,'এটি বৃষ্টির প্রস্তুতির নির্দেশনা। সরকারি বন্যা সতর্কতার জন্য সরকারি বুলেটিন দেখুন।')}</p>
      </section>}
      <section className="panel"><h3>{t('Official flood information','সরকারি বন্যার তথ্য')}</h3>
        <p>{t('Read the latest river-level warnings and flood bulletins directly from the Flood Forecasting and Warning Centre.','নদীর পানি ও বন্যার সরকারি সতর্কতা জানতে বন্যা পূর্বাভাস ও সতর্কীকরণ কেন্দ্রের বুলেটিন দেখুন।')}</p>
        <a href="https://www.ffwc.gov.bd/" target="_blank" rel="noreferrer" className="btn secondary">{t('Visit BWDB FFWC','সরকারি বুলেটিন দেখুন')} <ArrowUpRight size={16}/></a>
      </section>
    </div>
  </>;
}
