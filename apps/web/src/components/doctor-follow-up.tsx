'use client';

import Image from 'next/image';
import {useEffect, useRef, useState} from 'react';
import './doctor-follow-up.css';
import {useQueryClient} from '@tanstack/react-query';
import {Camera, Images, LoaderCircle} from 'lucide-react';
import {API, ApiError, getSessionToken, request} from '@/lib/api';
import type {Case, DoctorScreening} from '@/lib/types';

type Props = {
  result: DoctorScreening;
  locale: 'en' | 'bn';
  originalFile?: File;
  originalPreview?: string;
  onUpdate?: (result: DoctorScreening) => void;
};

export function DoctorFollowUp({result, locale, originalFile, originalPreview, onUpdate}: Props) {
  const bn = locale === 'bn';
  const t = (en: string, be: string) => bn ? be : en;
  const cache = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const flight = useRef<AbortController | null>(null);
  const [photo, setPhoto] = useState<File>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [thumb, setThumb] = useState('');
  const [open, setOpen] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const paired = result.photo_count === 2 || result.second_photo_available === true;
  const id = result.id;
  // For saved cases, always show the server copy after a concurrent update.
  const localPhoto = paired && id ? undefined : photo;

  useEffect(() => () => flight.current?.abort(), []);
  useEffect(() => {
    if (!localPhoto && !(open && id && result.second_photo_available)) return;
    const controller = new AbortController();
    let url = '';
    async function load() {
      try {
        let blob: Blob;
        if (localPhoto) blob = localPhoto;
        else {
          const response = await fetch(API + '/doctor/cases/' + id + '/image?view=follow_up', {
            headers: {Authorization: 'Bearer ' + getSessionToken()}, signal: controller.signal,
          });
          if (!response.ok) throw new Error('Photo unavailable');
          blob = await response.blob();
        }
        if (!controller.signal.aborted) {
          url = URL.createObjectURL(blob);
          setThumb(url);
          setImageFailed(false);
        }
      } catch {
        if (!controller.signal.aborted) setImageFailed(true);
      }
    }
    void load();
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [localPhoto, open, id, result.second_photo_available]);

  async function review() {
    if (!photo || paired || flight.current || (!id && !originalFile)) return;
    const controller = new AbortController();
    flight.current = controller;
    setPending(true);
    setError('');
    const form = new FormData();
    form.append('locale', locale);
    let route = '/doctor/cases';
    if (id) {
      route += '/' + id + '/follow-up';
      form.append('image', photo);
    } else {
      form.append('image', originalFile!);
      form.append('follow_up_image', photo);
      form.append('crop', result.crop);
      if (result.farmer_context) form.append('farmer_context', JSON.stringify(result.farmer_context));
    }
    try {
      const updated = await request<DoctorScreening>(route, {method: 'POST', body: form, signal: controller.signal});
      if (controller.signal.aborted) return;
      const next = {...updated, initial_assessment: updated.initial_assessment ?? result.assessment};
      if (id) {
        setThumb('');
        cache.setQueryData<Case>(['case', id], previous => previous ? {...previous, ...next} : previous);
        void cache.invalidateQueries({queryKey: ['actions']});
        void cache.invalidateQueries({queryKey: ['cases']});
      }
      onUpdate?.(next);
    } catch (cause) {
      if (controller.signal.aborted) return;
      let message = cause instanceof Error ? cause.message : 'Could not review both photos.';
      if (bn) {
        const errors: Record<number, string> = {
          0: 'সংযোগ পাওয়া যায়নি। ইন্টারনেট সংযোগ দেখে আবার চেষ্টা করুন।',
          401: 'আবার সাইন ইন করে ছবিটি দিন।',
          409: 'এই পরীক্ষায় ইতিমধ্যে দ্বিতীয় ছবি যোগ হয়েছে।',
          410: 'প্রথম ছবিটি পাওয়া যাচ্ছে না। নতুন পরীক্ষা শুরু করুন।',
          413: 'আট মেগাবাইটের মধ্যে একটি ছবি দিন।',
          415: 'একটি পরিষ্কার JPG, PNG বা WebP ছবি দিন।',
          422: 'দুইটি ছবিতে একই ফসল নিশ্চিত করা যায়নি। একই গাছ বা সবজির আরেকটি ছবি দিন।',
          429: 'এই মুহূর্তে পরীক্ষার সীমা পূর্ণ। একটু পরে আবার চেষ্টা করুন।',
        };
        message = (cause instanceof ApiError && errors[cause.status]) || 'দুইটি ছবি পরীক্ষা করা যায়নি। একটু পরে আবার চেষ্টা করুন।';
      }
      setError(message);
      if (id && cause instanceof ApiError && cause.status === 409) {
        const current = await request<Case>('/doctor/cases/' + id, {signal: controller.signal}).catch(() => null);
        if (current && !controller.signal.aborted) {
          cache.setQueryData(['case', id], current);
          onUpdate?.(current);
        }
      }
    } finally {
      flight.current = null;
      if (!controller.signal.aborted) setPending(false);
    }
  }

  if (paired) return <div className="doctor-followup">
    <strong><Images size={17}/> {t('Both photos reviewed together', 'দুইটি ছবি একসঙ্গে পরীক্ষা করা হয়েছে')}</strong>
    <details onToggle={e => setOpen(e.currentTarget.open)}>
      <summary>{t('See the second photo and the first assessment', 'দ্বিতীয় ছবি ও প্রথম পরীক্ষার ফল দেখুন')}</summary>
      {open && <div className="stack">
        <div className="doctor-followup-views">
          <figure>
            <figcaption>{t('Original view', 'প্রথম ছবি')}</figcaption>
            {originalPreview
              ? <Image unoptimized width={360} height={240} src={originalPreview} alt={t('Original crop photo', 'ফসলের প্রথম ছবি')}/>
              : <small>{t('Original photo unavailable.', 'প্রথম ছবিটি পাওয়া যাচ্ছে না।')}</small>}
          </figure>
          <figure>
            <figcaption>{t('Second view', 'দ্বিতীয় ছবি')}</figcaption>
            {imageFailed || (id && !result.second_photo_available)
              ? <small>{t('Second photo unavailable.', 'দ্বিতীয় ছবিটি পাওয়া যাচ্ছে না।')}</small>
              : thumb
                ? <Image unoptimized width={360} height={240} src={thumb} alt={t('Second crop photo', 'ফসলের দ্বিতীয় ছবি')}/>
                : <small role="status">{t('Opening photo…', 'ছবিটি খোলা হচ্ছে…')}</small>}
          </figure>
        </div>
        {result.initial_assessment && <p lang={result.initial_screening_locale}>
          <strong>{t('First assessment', 'প্রথম পরীক্ষার ফল')}</strong><br/>{result.initial_assessment.explanation}
        </p>}
      </div>}
    </details>
  </div>;

  if (!id && !originalFile) return null;
  if (id && result.image_available === false) return <p className="helper">{t(
    'The first photo is unavailable. Start a new screening to compare two views.',
    'প্রথম ছবিটি পাওয়া যাচ্ছে না। দুইটি ছবি তুলনা করতে নতুন পরীক্ষা শুরু করুন।')}</p>;

  return <div className="doctor-followup">
    <h3>{t('Add a second photo', 'দ্বিতীয় ছবি যোগ করুন')}</h3>
    <p>{t('Use another view of the same crop or item. If the first photo shows the whole plant, move closer to the damage. Groq will review both photos together.',
      'একই গাছ বা সবজির অন্য দিকের ছবি দিন। প্রথম ছবিতে পুরো গাছ থাকলে এবার আক্রান্ত অংশটি কাছ থেকে তুলুন। গ্রক দুইটি ছবি একসঙ্গে পরীক্ষা করবে।')}</p>
    <input type="file" ref={input} hidden accept="image/jpeg,image/png,image/webp" disabled={pending}
      aria-label={t('Second crop photo', 'ফসলের দ্বিতীয় ছবি')}
      onChange={e => {
        const picked = e.currentTarget.files?.[0];
        e.currentTarget.value = '';
        if (!picked) return;
        setThumb(''); setError(''); setImageFailed(false);
        if (!picked.size || picked.size > 8*1024*1024 || !['image/jpeg','image/png','image/webp'].includes(picked.type)) {
          setPhoto(undefined);
          setError(t('Choose a JPG, PNG or WebP photo up to 8 MB.', '৮ মেগাবাইটের মধ্যে JPG, PNG বা WebP ছবি দিন।'));
        } else setPhoto(picked);
      }}/>
    {photo && thumb && <Image unoptimized width={360} height={240} src={thumb} alt={t('Second photo to review', 'পরীক্ষার জন্য দ্বিতীয় ছবি')}/>}
    <div className="row wrap">
      <button type="button" className="btn secondary" disabled={pending} onClick={() => input.current?.click()}>
        <Camera size={16}/>{photo ? t('Change second photo','দ্বিতীয় ছবি বদলান') : t('Choose second photo','দ্বিতীয় ছবি বাছুন')}
      </button>
      {photo && <button type="button" className="btn primary" onClick={() => void review()} disabled={pending}>
        {pending && <LoaderCircle size={16} className="spin"/>}{pending ? t('Reviewing…','পরীক্ষা চলছে…') : t('Review both photos','দুইটি ছবি পরীক্ষা করুন')}
      </button>}
    </div>
    {pending && <div className="doctor-followup-progress" role="status">
      <span aria-hidden="true"/>{t('Reviewing your two crop photos…', 'ফসলের দুইটি ছবি পরীক্ষা করা হচ্ছে…')}
    </div>}
    {error && <p role="alert" className="error">{error}</p>}
  </div>;
}

