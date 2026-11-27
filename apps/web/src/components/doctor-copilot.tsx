'use client';

import Link from 'next/link';
import {useId, useRef, useState, type FormEvent} from 'react';
import {useQuery, useQueryClient} from '@tanstack/react-query';
import {ArrowRight, CalendarClock, Camera, ClipboardCheck, FlaskConical, LoaderCircle, MessageCircle, Phone, ScanLine} from 'lucide-react';
import {ApiError, formatDateOnly, formatTime, request} from '@/lib/api';
import type {Case, DoctorChange, DoctorReminder, DoctorScreening} from '@/lib/types';
import {DoctorFollowUp} from './doctor-follow-up';
import styles from './doctor-copilot.module.css';

type Locale = 'en' | 'bn';
type Stage = 'photos' | 'treatment' | 'check-in' | 'reminder';
type Props = {
  result: DoctorScreening;
  locale: Locale;
  visionAvailable: boolean;
  originalFile?: File;
  originalPreview?: string;
  onUpdate?: (result: DoctorScreening) => void;
  onAsk: (topic?: 'screening' | 'treatment') => void;
};

const changes: Record<DoctorChange, [string, string]> = {
  improving: ['Improving', 'ভালো হচ্ছে'],
  unchanged: ['About the same', 'প্রায় একই আছে'],
  worsening: ['Getting worse', 'খারাপ হচ্ছে'],
  unsure: ['Not sure', 'নিশ্চিত নই'],
};

function bangladeshDate() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Dhaka', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date());
  return ['year', 'month', 'day'].map(key => parts.find(part => part.type === key)?.value).join('-');
}

export function DoctorCopilot({result, locale, visionAvailable, originalFile, originalPreview, onUpdate, onAsk}: Props) {
  const t = (english: string, bangla: string) => locale === 'bn' ? bangla : english;
  const changeText = (change: DoctorChange) => t(...changes[change]);
  const titleId = useId();
  const panelId = useId();
  const queries = useQueryClient();
  const id = result.id;
  const path = '/doctor/cases/' + encodeURIComponent(id ?? '');
  const [stage, setStage] = useState<Stage>(() =>
    result.treatment_guidance?.[locale].status === 'registry_reference' ? 'treatment' : 'photos');
  const [change, setChange] = useState<DoctorChange | ''>('');
  const [note, setNote] = useState('');
  const [dateDraft, setDateDraft] = useState<string | null>(null);
  const [pending, setPending] = useState<Stage | null>(null);
  const [feedback, setFeedback] = useState<{stage: Stage; error: boolean; message: string} | null>(null);
  const actionInFlight = useRef(false);
  const checkIn = useRef<{signature: string; id: string} | null>(null);
  const detail = useQuery({
    queryKey: ['case', id],
    queryFn: ({signal}) => request<Case>(path, {signal}),
    enabled: !!id,
    staleTime: 25_000,
  });
  const checkIns = detail.data?.check_ins ?? [];
  const treatment = (result.treatment_guidance ?? detail.data?.treatment_guidance)?.[locale];
  const latest = checkIns[0];
  const reminder = detail.data?.follow_up_reminder;
  const date = dateDraft ?? reminder?.due_on ?? '';
  const today = bangladeshDate();
  const paired = result.photo_count === 2 || result.second_photo_available === true;
  const photosAvailable = paired || (visionAvailable && (id
    ? result.model.model_id === 'groq-vision' && !!result.assessment
    : !!originalFile && !!result.assessment));
  const produce = result.assessment?.part === 'produce' || result.model.model_id === 'agrodoctor-research-produce';
  const tabs = [
    {id: 'photos', icon: Camera, label: t('Compare photos', 'ছবি তুলনা')},
    {id: 'treatment', icon: FlaskConical, label: t('Treatment', 'প্রতিকার')},
    {id: 'check-in', icon: ClipboardCheck, label: t('Check-in', 'পর্যবেক্ষণ')},
    {id: 'reminder', icon: CalendarClock, label: t('Reminder', 'রিমাইন্ডার')},
  ] as const;

  async function update(active: Stage, operation: () => Promise<unknown>, success: string) {
    if (!id || actionInFlight.current) return false;
    actionInFlight.current = true;
    setPending(active);
    setFeedback(null);
    try {
      await operation();
      await Promise.all([
        queries.invalidateQueries({queryKey: ['case', id], exact: true}),
        ...(active === 'reminder' ? [queries.invalidateQueries({queryKey: ['farm-tools']})] : []),
      ]);
      setFeedback({stage: active, error: false, message: success});
      return true;
    } catch (error) {
      const message = error instanceof ApiError && error.status === 401
        ? t('Sign in again to continue.', 'চালিয়ে যেতে আবার সাইন ইন করুন।')
        : error instanceof ApiError && error.status === 404
          ? t('This case or reminder is no longer available. Reload the case.', 'এই পরীক্ষা বা রিমাইন্ডারটি আর পাওয়া যাচ্ছে না। পৃষ্ঠাটি আবার খুলুন।')
          : t('Could not save your change. Try again.', 'পরিবর্তন সংরক্ষণ করা যায়নি। আবার চেষ্টা করুন।');
      setFeedback({stage: active, error: true, message});
      return false;
    } finally {
      actionInFlight.current = false;
      setPending(null);
    }
  }

  async function saveCheckIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!change || actionInFlight.current) return;
    const value = note.trim();
    const signature = JSON.stringify([change, value]);
    if (checkIn.current?.signature !== signature) {
      const random = crypto.getRandomValues(new Uint32Array(4));
      checkIn.current = {signature, id: Array.from(random, part => part.toString(16).padStart(8, '0')).join('')};
    }
    const requestId = checkIn.current.id;
    if (await update('check-in', () => request(path + '/check-ins', {
      method: 'POST', body: JSON.stringify({request_id: requestId, change, note: value}),
    }), t('Check-in saved.', 'পর্যবেক্ষণ সংরক্ষিত হয়েছে।'))) {
      setChange('');
      setNote('');
      checkIn.current = null;
    }
  }

  async function saveReminder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!date || date < today) return;
    if (await update('reminder', () => request<DoctorReminder>(path + '/reminder', {
      method: 'POST', body: JSON.stringify({due_on: date, locale}),
    }), t('Recheck reminder saved.', 'আবার দেখার রিমাইন্ডার সংরক্ষিত হয়েছে।'))) setDateDraft(null);
  }

  async function removeReminder() {
    if (!reminder) return;
    if (await update('reminder', () => request('/farm-tools/records/farm_reminder/' + encodeURIComponent(reminder.id),
      {method: 'DELETE'}), t('Reminder removed.', 'রিমাইন্ডার সরানো হয়েছে।'))) setDateDraft(null);
  }

  const showFeedback = (active: Stage) => feedback?.stage === active && <p
    className={feedback.error ? styles.error : styles.success} role={feedback.error ? 'alert' : 'status'}>{feedback.message}</p>;
  const readError = id && detail.isError && <div className={styles.error} role="alert">
    {t('Could not refresh follow-up records.', 'পর্যবেক্ষণের তথ্য আবার আনা যায়নি।')}
    <button className="text-link" type="button" onClick={() => void detail.refetch()}>{t('Try again', 'আবার চেষ্টা করুন')}</button>
  </div>;

  return <section className={styles.copilot} aria-labelledby={titleId}>
    <header className={styles.hero}>
      <div className={styles.mark} aria-hidden="true"><ScanLine size={30}/><span/></div>
      <div>
        <h3 id={titleId}>{t('AgroDoctor Follow-up Copilot', 'অ্যাগ্রোডক্টর ফলো-আপ সহায়ক')}</h3>
        <p>{t('Compare photos, record what changed, and plan your next check.', 'ছবি মেলান, কী পরিবর্তন হয়েছে লিখুন, আর আবার দেখার সময় ঠিক করুন।')}</p>
      </div>
      <span className={styles.caseState}>{id ? t('Saved case', 'সংরক্ষিত পরীক্ষা') : t('Preview', 'প্রাথমিক ফল')}</span>
    </header>
    <div className={styles.stages} role="group" aria-label={t('Follow-up steps', 'ফলো-আপের ধাপ')}>
      {tabs.map(({id: value, label, icon: Icon}) => <button key={value} type="button"
        aria-pressed={stage === value} aria-controls={panelId + value} onClick={() => setStage(value)}>
        <Icon size={17} aria-hidden="true"/><span>{label}</span>
      </button>)}
    </div>

    <div className={styles.panel} id={panelId + 'treatment'} hidden={stage !== 'treatment'}>
      <h4>{t('Treatment guidance', 'প্রতিকারের নির্দেশনা')}</h4>
      {treatment ? <>
        <p>{treatment.summary}</p>
        {treatment.products.length > 0 && <div className={styles.registry}>
          <strong>{t('DAE-listed examples to discuss with your adviser', 'কৃষি কর্মকর্তার সঙ্গে আলোচনার জন্য ডিএইর তালিকার উদাহরণ')}</strong>
          <ul>{treatment.products.map(product => <li key={product.registration}>
            <span>{product.name}<small>{product.ingredient}</small></span>
            <span className={styles.registration}>{product.registration}</span>
          </li>)}</ul>
        </div>}
        {treatment.steps.length > 0 && <ul className={styles.treatmentSteps}>
          {treatment.steps.map(step => <li key={step}>{step}</li>)}
        </ul>}
        {treatment.sources.length > 0 && <div className={styles.treatmentSources}>
          {treatment.sources.map(source => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">
            {source.label}
          </a>)}
        </div>}
      </> : <p>{t('Reopen or run a screening to load its treatment guidance.', 'প্রতিকারের নির্দেশনা দেখতে পরীক্ষাটি আবার খুলুন বা নতুন পরীক্ষা করুন।')}</p>}
      <div className={styles.formActions}>
        <button type="button" className="btn secondary" onClick={() => onAsk('treatment')}>
          <MessageCircle size={15} aria-hidden="true"/>{t('Ask about treatment', 'প্রতিকার নিয়ে প্রশ্ন করুন')}
        </button>
        {treatment?.status !== 'monitor' && <a href="tel:16123" className="btn secondary">
          <Phone size={15} aria-hidden="true"/>{t('Call an adviser · 16123', 'কৃষি কল সেন্টার · ১৬১২৩')}
        </a>}
      </div>
    </div>

    <div className={styles.panel} id={panelId + 'photos'} hidden={stage !== 'photos'}>
      {photosAvailable
        ? <DoctorFollowUp result={result} locale={locale} originalFile={originalFile} originalPreview={originalPreview} onUpdate={onUpdate}/>
        : <>
          <h4>{t('Take a comparable photo', 'তুলনা করার মতো ছবি তুলুন')}</h4>
          <p>{produce
            ? t('Photograph the same item from another angle in even light. Check other items from the same batch.', 'একই ফল বা কন্দ সমান আলোতে অন্য দিক থেকে তুলুন। একই ব্যাচের অন্যগুলোও দেখুন।')
            : t('Photograph the same plant from the same distance and in similar light. Include the affected area and nearby healthy tissue.', 'একই গাছ কাছাকাছি দূরত্ব ও একই ধরনের আলোতে তুলুন। আক্রান্ত অংশের পাশে সুস্থ অংশটিও রাখুন।')}</p>
          <p className={styles.muted}>{t('This result can be used as a reference for your next screening.', 'পরের পরীক্ষায় এই ফলের সঙ্গে লক্ষণগুলো মিলিয়ে দেখুন।')}</p>
          {id && <Link className="text-link" href={'/' + locale + '/agrodoctor'}>
            {t('Start another screening', 'নতুন পরীক্ষা শুরু করুন')} <ArrowRight size={15} aria-hidden="true"/>
          </Link>}
        </>}
      {paired && <p className={styles.muted}>{t('Two photo views support the screening. Use a check-in to record when you actually see a change.',
        'দুই দিকের ছবি পরীক্ষায় সহায়তা করে। মাঠে সত্যিই পরিবর্তন দেখলে পর্যবেক্ষণে লিখুন।')}</p>}
    </div>

    <div className={styles.panel} id={panelId + 'check-in'} hidden={stage !== 'check-in'}>
      <h4>{t('How does it look today?', 'আজ দেখতে কেমন?')}</h4>
      {id ? <>
        <p>{t('Compare the same area with your previous visit. Your observations are saved separately from the screening.', 'আগেরবার দেখা একই অংশের সঙ্গে মিলিয়ে দেখুন। আপনার পর্যবেক্ষণ পরীক্ষার ফল থেকে আলাদা করে সংরক্ষণ হবে।')}</p>
        <form className={styles.form} onSubmit={saveCheckIn} aria-busy={pending === 'check-in'}>
          <fieldset className={styles.choices} disabled={pending !== null}>
            <legend>{t('Change since your last check', 'গতবার দেখার পর পরিবর্তন')}</legend>
            <div>{(Object.keys(changes) as DoctorChange[]).map(value => <label key={value}>
              <input type="radio" name={panelId + '-change'} value={value} checked={change === value}
                onChange={() => setChange(value)} required/>{changeText(value)}
            </label>)}</div>
          </fieldset>
          <label>{t('What did you notice? (optional)', 'কী লক্ষ্য করেছেন? (ঐচ্ছিক)')}
            <textarea rows={2} maxLength={2000} value={note} disabled={pending !== null} onChange={event => setNote(event.target.value)}/>
          </label>
          <button className="btn primary" type="submit" disabled={!change || pending !== null}>
            {pending === 'check-in' && <LoaderCircle size={16} className="spin" aria-hidden="true"/>}
            {pending === 'check-in' ? t('Saving…', 'সংরক্ষণ হচ্ছে…') : t('Save check-in', 'পর্যবেক্ষণ সংরক্ষণ')}
          </button>
        </form>
        {showFeedback('check-in')}
        {readError}
        {checkIns.length > 0 && <div className={styles.log}>
          <h4>{t('Check-in history', 'আগের পর্যবেক্ষণ')}</h4>
          <ul>{checkIns.slice(0, 3).map(entry => <li key={entry.id}>
            <div><strong>{changeText(entry.change)}</strong>
              <time dateTime={entry.created_at}>{formatTime(entry.created_at, locale)}</time></div>
            {entry.note && <p>{entry.note}</p>}
          </li>)}</ul>
          {checkIns.length > 3 && <details>
            <summary>{t('Show older check-ins', 'আরও পুরোনো পর্যবেক্ষণ দেখুন')}</summary>
            <ul>{checkIns.slice(3).map(entry => <li key={entry.id}><div><strong>{changeText(entry.change)}</strong>
              <time dateTime={entry.created_at}>{formatTime(entry.created_at, locale)}</time></div>
              {entry.note && <p>{entry.note}</p>}
            </li>)}</ul>
          </details>}
        </div>}
        {latest?.change === 'worsening' && <div className={styles.adviser}>
          <p>{t('You reported that it is getting worse. Show your photos and check-in to an agricultural adviser.', 'আপনার পর্যবেক্ষণে অবস্থা খারাপ হচ্ছে। ছবি ও পর্যবেক্ষণ কৃষি কর্মকর্তাকে দেখান।')}</p>
          <a href="tel:16123"><Phone size={15} aria-hidden="true"/>{t('Call an adviser · 16123', 'কৃষি কল সেন্টার · ১৬১২৩')}</a>
        </div>}
      </> : <p>{t('Save a screening to a plot to record dated check-ins.', 'তারিখসহ পর্যবেক্ষণ রাখতে জমিতে পরীক্ষার ফল সংরক্ষণ করুন।')}</p>}
    </div>

    <div className={styles.panel} id={panelId + 'reminder'} hidden={stage !== 'reminder'}>
      <h4>{t('Plan your next recheck', 'আবার দেখার সময় ঠিক করুন')}</h4>
      {id && result.plot_id ? <>
        <p>{t('Choose a date that works for you. The reminder appears in Farm tools for this plot.', 'সুবিধামতো তারিখ বেছে নিন। রিমাইন্ডারটি এই জমির খামারের টুলে দেখাবে।')}</p>
        {reminder && <p className={styles.reminderLine}><CalendarClock size={16} aria-hidden="true"/>
          {t('Scheduled for', 'নির্ধারিত তারিখ')} <strong>{formatDateOnly(reminder.due_on, locale)}</strong></p>}
        <form className={styles.form} onSubmit={saveReminder} aria-busy={pending === 'reminder'}>
          <label>{t('Recheck date', 'আবার দেখার তারিখ')}
            <input type="date" min={today} value={date} disabled={pending !== null} required onChange={event => setDateDraft(event.target.value)}/>
          </label>
          <div className={styles.formActions}>
            <button className="btn primary" type="submit" disabled={!date || date < today || pending !== null}>
              {pending === 'reminder' && <LoaderCircle size={16} className="spin" aria-hidden="true"/>}
              {reminder ? t('Update reminder', 'রিমাইন্ডার বদলান') : t('Save reminder', 'রিমাইন্ডার সংরক্ষণ')}
            </button>
            {reminder && <button className="btn secondary" type="button" disabled={pending !== null} onClick={() => void removeReminder()}>
              {t('Remove reminder', 'রিমাইন্ডার সরান')}
            </button>}
          </div>
        </form>
        {showFeedback('reminder')}
        {readError}
      </> : <p>{t('A saved screening with a plot is needed for a recheck reminder.', 'আবার দেখার রিমাইন্ডার রাখতে জমিতে পরীক্ষার ফল সংরক্ষণ করুন।')}</p>}
    </div>
    <footer className={styles.footer}>
      <MessageCircle size={18} aria-hidden="true"/>
      <div>
        <strong>{t('Questions about your result?', 'ফল নিয়ে প্রশ্ন আছে?')}</strong>
        <p>{t('Farmer Chat can use this screening to suggest what to check next.', 'এরপর কী দেখবেন, এই ফলের ভিত্তিতে কৃষি সহায়কের কাছে জানতে পারেন।')}</p>
      </div>
      <button type="button" className="btn secondary" onClick={() => onAsk()}>
        {t('Ask about this screening','এই পরীক্ষার ফল নিয়ে প্রশ্ন করুন')} <ArrowRight size={15} aria-hidden="true"/>
      </button>
    </footer>
  </section>;
}
