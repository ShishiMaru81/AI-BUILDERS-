'use client';

import Link from 'next/link';
import {useRef, useState, type FormEvent} from 'react';
import {useQuery} from '@tanstack/react-query';
import {ArrowRight, Leaf, LoaderCircle, ShieldCheck} from 'lucide-react';
import {request, setSessionToken} from '@/lib/api';

type Locale = 'en' | 'bn';
type Role = 'farmer' | 'customer' | 'admin';
type Purpose = 'login' | 'signup';

function photoBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
    reader.onerror = () => reject(new Error('Could not read the photo.'));
    reader.readAsDataURL(file);
  });
}

export function AccountAccess({locale, marketplace = false}: {locale: Locale; marketplace?: boolean}) {
  const t = (en: string, bn: string) => locale === 'bn' ? bn : en;
  const [purpose, setPurpose] = useState<Purpose>('login');
  const [channel, setChannel] = useState<'phone' | 'email'>('phone');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [age, setAge] = useState('');
  const [role, setRole] = useState<'farmer' | 'customer'>('customer');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const options = useQuery({
    queryKey: ['auth-options'],
    queryFn: () => request<{demo: boolean}>('/auth/options'),
    enabled: !marketplace,
  });
  const contact = channel === 'phone' ? phone : email;
  const mobileFormat = t('Include +880. Enter exactly 14 characters, including +, as in +8801712345678.',
    '+৮৮০ সহ লিখুন। + চিহ্নসহ ঠিক ১৪টি অক্ষর দিন, যেমন +৮৮০১৭১২৩৪৫৬৭৮।');
  const nidFormat = t('Enter exactly 10, 13, or 17 digits.', 'ঠিক ১০, ১৩ অথবা ১৭টি অঙ্ক লিখুন।');
  function finish({token, user}: {token: string; user: {role: Role}}) {
    setSessionToken(token);
    const dest = user.role === 'admin' ? 'marketplace/admin'
      : marketplace || user.role === 'customer' ? 'marketplace' : 'dashboard';
    window.location.assign(`/${locale}/${dest}`);
  }

  async function run(action: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('Please try again.', 'আবার চেষ্টা করুন।'));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fields = new FormData(e.currentTarget);
    await run(async () => {
      if (purpose === 'login') {
        finish(await request<Parameters<typeof finish>[0]>('/auth/password', {
          method: 'POST', body: JSON.stringify({contact, password: fields.get('password')}),
        }));
        return;
      }
      const password = String(fields.get('password') || '');
      const confirmPassword = String(fields.get('confirm_password') || '');
      if (password !== confirmPassword) throw new Error(t('Passwords must match.', 'পাসওয়ার্ড দুটি মিলতে হবে।'));
      const photo = fields.get('photo');
      if (!(photo instanceof File) || !photo.size || photo.size > 1024 * 1024) {
        throw new Error(t('Choose a portrait photo up to 1 MB.', 'সর্বোচ্চ ১ এমবির একটি পাসপোর্ট আকারের ছবি বেছে নিন।'));
      }
      const profile = {
        name, age: Number(age), role,
        national_id: String(fields.get('national_id') || ''),
        permanent_address: String(fields.get('permanent_address') || ''),
        present_address: String(fields.get('present_address') || ''),
        ward_number: String(fields.get('ward_number') || ''),
        gender: String(fields.get('gender') || ''),
        photo_base64: await photoBase64(photo),
        password,
        confirm_password: confirmPassword,
      };
      finish(await request<Parameters<typeof finish>[0]>('/auth/signup', {
        method: 'POST', body: JSON.stringify({contact, profile}),
      }));
    });
  }

  return <main className="account-access">
    <section className="account-brand">
      <div className="account-farm-art" aria-hidden="true"/>
      <div className="account-brand-copy">
        <div className="account-mark"><Leaf size={24}/> AgroSphere AI</div>
        <h1>
          <span className="account-headline-line"><span>{t('From farm', 'খামার থেকে')}</span></span>{' '}
          <span className="account-headline-line"><span>{t('to market', 'বাজারে')}</span></span>
        </h1>
        <p>{t('Screen crop leaves, sell your harvest, or buy directly from growers.', 'ফসলের পাতা পরীক্ষা করুন, ফসল বিক্রি করুন অথবা কৃষকের কাছ থেকে কিনুন।')}</p>
        <Link className="account-language" href={`/${locale === 'en' ? 'bn' : 'en'}${marketplace ? '/marketplace/auth' : ''}`}>
          {locale === 'en' ? 'বাংলা' : 'English'}
        </Link>
      </div>
    </section>
    <section className="account-form" aria-labelledby="account-title">
      <div className="account-mode" data-purpose={purpose} role="group" aria-label={t('Account options', 'অ্যাকাউন্টের বিকল্প')}>
        {(['login', 'signup'] as const).map(mode => <button key={mode} type="button"
          aria-pressed={purpose === mode} disabled={busy} onClick={() => {
            setPurpose(mode);
            setError('');
          }}>
          {mode === 'login' ? t('Sign in', 'প্রবেশ করুন') : t('Sign up', 'অ্যাকাউন্ট খুলুন')}
        </button>)}
      </div>
      <h2 id="account-title" className="ui-reveal" key={purpose}>{purpose === 'signup' ? t('Create your account', 'অ্যাকাউন্ট তৈরি করুন') : t('Sign in to AgroSphere', 'অ্যাগ্রোস্ফিয়ারে প্রবেশ করুন')}</h2>
      <form onSubmit={submit} className="account-fields" aria-busy={busy}>
        {purpose === 'signup' && <>
          <label>{t('Full name', 'পুরো নাম')}<input autoComplete="name" value={name} onChange={e => setName(e.target.value)} maxLength={120} required disabled={busy}/></label>
          <label>{t('Age in years', 'বয়স (বছর)')}<input type="number" min={1} max={120} step={1} value={age} onChange={e => setAge(e.target.value)} required disabled={busy}/></label>
          <label>{t('Account type', 'অ্যাকাউন্টের ধরন')}<select value={role} onChange={e => setRole(e.target.value === 'farmer' ? 'farmer' : 'customer')} disabled={busy}>
            <option value="customer">{t('Customer · Buy produce', 'ক্রেতা · পণ্য কিনুন')}</option>
            <option value="farmer">{t('Farmer · Sell produce and use AgroDoctor', 'কৃষক · পণ্য বিক্রি ও অ্যাগ্রোডক্টর ব্যবহার করুন')}</option>
          </select></label>
          <fieldset className="account-identity ui-reveal" disabled={busy}>
            <legend>{t('Private signup details', 'নিবন্ধনের ব্যক্তিগত তথ্য')}</legend>
            <label>{t('Bangladesh national ID number', 'বাংলাদেশের জাতীয় পরিচয়পত্র নম্বর')}
              <input name="national_id" inputMode="numeric" autoComplete="off"
                pattern="(?:[0-9০-৯]{10}|[0-9০-৯]{13}|[0-9০-৯]{17})" required
                aria-describedby="nid-format" title={nidFormat}/>
              <small id="nid-format">{nidFormat}</small>
            </label>
            <label>{t('Gender', 'লিঙ্গ')}<select name="gender" defaultValue="" required>
              <option value="" disabled>{t('Choose an option', 'বেছে নিন')}</option>
              <option value="male">{t('Male', 'পুরুষ')}</option>
              <option value="female">{t('Female', 'মহিলা')}</option>
            </select></label>
            <label>{t('Permanent address', 'স্থায়ী ঠিকানা')}<textarea name="permanent_address" rows={2} minLength={5} maxLength={500} required/></label>
            <label>{t('Present address', 'বর্তমান ঠিকানা')}<textarea name="present_address" rows={2} minLength={5} maxLength={500} required/></label>
            <label>{t('Ward number', 'ওয়ার্ড নম্বর')}<input name="ward_number" inputMode="numeric" pattern="[0-9]{1,4}" required/></label>
            <label>{t('Passport-size photo', 'পাসপোর্ট আকারের ছবি')}<input name="photo" type="file" accept="image/jpeg,image/png,image/webp" required/></label>
            <small>{t('JPG, PNG, or WebP up to 1 MB. These details stay private.', 'জেপিজি, পিএনজি বা ওয়েবপি, সর্বোচ্চ ১ এমবি। এই তথ্য ব্যক্তিগত থাকবে।')}</small>
            <label>{t('Set password', 'পাসওয়ার্ড দিন')}<input name="password" type="password" autoComplete="new-password" minLength={10} maxLength={128} required/></label>
            <label>{t('Confirm password', 'পাসওয়ার্ড আবার লিখুন')}<input name="confirm_password" type="password" autoComplete="new-password" minLength={10} maxLength={128} required/></label>
          </fieldset>
        </>}
        <label>{t('Account contact', 'অ্যাকাউন্টের যোগাযোগের মাধ্যম')}<select
          value={channel} disabled={busy} onChange={e => {
            setChannel(e.target.value === 'email' ? 'email' : 'phone');
            setError('');
          }}
        >
          <option value="phone">{t('Mobile number', 'মোবাইল নম্বর')}</option>
          <option value="email">{t('Email', 'ইমেইল')}</option>
        </select></label>
        {channel === 'phone' ? <label>
          {t('Mobile number', 'মোবাইল নম্বর')}
          <input type="tel" autoComplete="tel" value={phone} placeholder="+8801712345678"
            onChange={e => setPhone(e.target.value.replace(/[০-৯]/g, digit => String(digit.charCodeAt(0) - 0x09e6)))}
            pattern={'\\+8801[0-9]{9}'} required disabled={busy}
            aria-describedby="bd-phone-hint" title={mobileFormat}/>
          <small id="bd-phone-hint">{mobileFormat}</small>
        </label> : <label>
          {t('Email address', 'ইমেইল ঠিকানা')}
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="email"
            autoCapitalize="none" spellCheck={false} maxLength={254} required disabled={busy}
            placeholder="name@gmail.com"/>
        </label>}
        {purpose === 'login' && <label>{t('Password', 'পাসওয়ার্ড')}
          <input name="password" type="password" autoComplete="current-password" required disabled={busy}/>
        </label>}
        <button className="btn primary" disabled={busy}>
          {purpose === 'signup' ? t('Create account', 'অ্যাকাউন্ট তৈরি করুন') : t('Sign in', 'প্রবেশ করুন')}
          {busy ? <LoaderCircle size={16} className="account-spinner" aria-hidden="true"/> : <ArrowRight size={16} aria-hidden="true"/>}
        </button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {options.data?.demo && !marketplace && <button type="button" className="btn secondary" disabled={busy}
        onClick={() => void run(async () => {
          const {token} = await request<{token: string}>('/auth/demo', {
            method: 'POST', body: JSON.stringify({name: t('Demo farmer', 'ডেমো কৃষক')}),
          });
          finish({token, user: {role: 'farmer'}});
        })}>
        <ShieldCheck size={16}/>{t('Explore a demo farm', 'ডেমো খামার দেখুন')}
      </button>}
    </section>
  </main>;
}
