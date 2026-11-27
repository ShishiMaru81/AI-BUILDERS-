'use client';

import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useRef, useState, type FormEvent} from 'react';
import {useQueryClient} from '@tanstack/react-query';
import {
  Activity, ArrowLeft, ArrowRight, Bell, ClipboardList, CloudRain, Database, Gavel, LayoutDashboard,
  LogOut, Package, ScanLine, Settings2, ShieldCheck, ShoppingCart, Sprout, Users, type LucideIcon,
} from 'lucide-react';
import {ApiError, FRONTEND_PREVIEW, formatTime, request, setSessionToken} from '@/lib/api';
import {useSession} from '@/lib/session';
import {AdminList, AdminPolicy, type AdminListKind} from './marketplace-admin';
import {DataState, MarketContext, useMarket, useMarketQuery} from './marketplace-shared';
import './marketplace.css';
import styles from './admin-console.module.css';

type Locale = 'en' | 'bn';
type Section = AdminListKind | 'overview' | 'activity' | 'system' | 'policy';
type Text = (english: string, bangla: string) => string;
type SectionEntry = {
  id: Section;
  icon: LucideIcon;
  name: [string, string];
  description: [string, string];
};

const sections: SectionEntry[] = [
  {id:'overview', icon:LayoutDashboard, name:['Overview','সারসংক্ষেপ'], description:['Accounts, farm activity and marketplace operations at a glance.','অ্যাকাউন্ট, খামার ও বাজারের কার্যক্রম এক নজরে দেখুন।']},
  {id:'users', icon:Users, name:['Users','ব্যবহারকারী'], description:['Review accounts, change account status and manage seller verification.','অ্যাকাউন্টের অবস্থা ও বিক্রেতা যাচাই পরিচালনা করুন।']},
  {id:'products', icon:Package, name:['Listings','পণ্য তালিকা'], description:['Review published and hidden listings and change their visibility.','প্রকাশিত ও লুকানো পণ্য পর্যালোচনা করুন।']},
  {id:'orders', icon:ShoppingCart, name:['Orders','অর্ডার'], description:['Review order details and intervene in eligible seller orders.','অর্ডারের বিবরণ দেখুন ও প্রযোজ্য অর্ডারে পদক্ষেপ নিন।']},
  {id:'auctions', icon:Gavel, name:['Auctions','নিলাম'], description:['Monitor auctions and cancel eligible lots with a recorded reason.','নিলাম দেখুন ও কারণ লিখে প্রযোজ্য লট বাতিল করুন।']},
  {id:'reports', icon:Bell, name:['Reports','রিপোর্ট'], description:['Review reports about marketplace listings and orders.','বাজারের পণ্য ও অর্ডার সম্পর্কিত রিপোর্ট পর্যালোচনা করুন।']},
  {id:'activity', icon:Sprout, name:['Farm activity','খামারের কার্যক্রম'], description:['Record counts across farms, crop screenings, weather, and other farm tools.','খামার, ফসল পরীক্ষা, আবহাওয়া ও অন্যান্য টুলের রেকর্ড সংখ্যা।']},
  {id:'audit', icon:ClipboardList, name:['Audit trail','অডিট ইতিহাস'], description:['Review recorded marketplace and administrative events.','বাজার ও প্রশাসনের নথিভুক্ত কার্যক্রম দেখুন।']},
  {id:'system', icon:Activity, name:['System status','সিস্টেমের অবস্থা'], description:['Check the configured AI models and the platform’s data mode.','এআই মডেল ও প্ল্যাটফর্মের ডেটা মোড দেখুন।']},
  {id:'policy', icon:Settings2, name:['Policies','নীতিমালা'], description:['Control marketplace availability, seller verification and transaction limits.','বাজারের প্রাপ্যতা, বিক্রেতা যাচাই ও লেনদেনের সীমা ঠিক করুন।']},
];

const groups = [
  {label: ['Workspace', 'কর্মক্ষেত্র'], items: sections.slice(0, 2)},
  {label: ['Marketplace', 'বাজার'], items: sections.slice(2, 6)},
  {label: ['Platform', 'প্ল্যাটফর্ম'], items: sections.slice(6)},
];

type OverviewData = {
  generated_at: string;
  accounts: {total: number; active: number; demo: number; farmer: number; customer: number; admin: number; other: number};
  records: Record<string, number>;
  marketplace: {listings: number; orders: number; auctions: number; open_reports: number; enabled: boolean};
};
type SystemData = {
  data_mode: string;
  chat_configured: boolean;
  models: {model_id: string; version: string; available: boolean; artifact_status: string}[];
};

const activity: [string, string, string, LucideIcon][] = [
  ['farm','Farms','খামার',Sprout], ['plot','Crop plots','ফসলের জমি',Sprout],
  ['case','AgroDoctor screenings','এগ্রোডক্টর পরীক্ষা',ScanLine],
  ['weather','Saved weather outlooks','সংরক্ষিত আবহাওয়ার পূর্বাভাস',CloudRain],
  ['price','Market price records','বাজারদরের রেকর্ড',Package],
  ['comparison','Price comparisons','দর তুলনা',Package],
  ['rescue_plan','Harvest plans','ফসলের পরিকল্পনা',ClipboardList],
  ['action','Farm tasks','খামারের কাজ',ClipboardList],
  ['farmer_chat','Farmer Chat conversations','কৃষি সহায়কের কথোপকথন',Users],
  ['farm_ledger','Farm ledger entries','খামারের হিসাব',ClipboardList],
  ['storage_batch','Storage batches','সংরক্ষিত ফসলের চালান',Package],
  ['farm_reminder','Farm reminders','খামারের স্মরণিকা',Bell],
  ['community_report','Community crop reports','ফসলের কমিউনিটি রিপোর্ট',Bell],
  ['device','Registered devices','নিবন্ধিত ডিভাইস',Database],
];

const adminPath = (locale: Locale, section: Section = 'overview') =>
  '/' + locale + '/admin' + (section === 'overview' ? '' : '/' + section);

export function AdminConsole({locale, section}: {locale: Locale; section?: string}) {
  const {state, user, refreshSession} = useSession();
  const t: Text = (english, bangla) => locale === 'bn' ? bangla : english;
  const current = sections.find(item => item.id === section) ?? sections[0];

  if (state === 'checking' || state === 'service_error') {
    return <main className={styles.access} lang={locale}>
      <section className={styles.accessCard}>
        <ShieldCheck size={28} aria-hidden="true"/>
        <h1>{t('Admin sign in','অ্যাডমিন সাইন ইন')}</h1>
        {state === 'checking' ? <p role="status">{t('Checking your session…','সেশন যাচাই হচ্ছে…')}</p>
          : <><p role="alert">{t('Could not check the session.','সেশন যাচাই করা যায়নি।')}</p>
            <button className={styles.primary} onClick={() => void refreshSession()}>{t('Try again','আবার চেষ্টা করুন')}</button></>}
      </section>
    </main>;
  }
  if (state !== 'authenticated' || user?.role !== 'admin') {
    return <AdminSignIn locale={locale} t={t} destination={current.id} accountIsRegular={state === 'authenticated'}/>;
  }
  return <AdminWorkspace key={user.id} current={current} locale={locale} t={t} userId={user.id} name={user.name}/>;
}

function AdminSignIn({locale, t, destination, accountIsRegular}: {
  locale: Locale; t: Text; destination: Section; accountIsRegular: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    const fields = new FormData(event.currentTarget);
    try {
      const result = await request<{token: string; user: {role: string}}>('/auth/admin/login', {
        method: 'POST', body: JSON.stringify({email: fields.get('email'), password: fields.get('password')}),
      });
      if (result.user.role !== 'admin') throw new ApiError('Administrator access required', 403);
      setSessionToken(result.token);
      window.location.replace(adminPath(locale, destination));
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 429
        ? t('Too many attempts. Wait a moment and try again.','অনেকবার চেষ্টা হয়েছে। একটু পরে আবার চেষ্টা করুন।')
        : cause instanceof ApiError && [401, 403, 422].includes(cause.status)
          ? t('Enter a valid administrator email and password.','অ্যাডমিনের সঠিক ইমেইল ও পাসওয়ার্ড দিন।')
          : t('Sign-in is temporarily unavailable. Try again.','এখন সাইন ইন করা যাচ্ছে না। আবার চেষ্টা করুন।'));
    } finally {
      setBusy(false);
      pending.current = false;
    }
  }

  return <main className={styles.access} lang={locale}>
    <div className={styles.accessLayout}>
      <div className={styles.accessSide}>
        <div className={styles.brand}><Sprout size={21} aria-hidden="true"/> AgroSphere AI</div>
        <ShieldCheck size={76} strokeWidth={1.05} className={styles.signMark} aria-hidden="true"/>
        <div><p>{t('Platform administration','প্ল্যাটফর্ম প্রশাসন')}</p>
          <span>{t('Manage access, review marketplace activity, and monitor farm tools.','অ্যাক্সেস, বাজারের কার্যক্রম ও খামারের টুল পরিচালনা করুন।')}</span>
        </div>
      </div>
      <section className={styles.accessCard} aria-labelledby="admin-sign-in">
        <div className={styles.accessHeader}>
          <Link href={'/' + locale}><ArrowLeft size={15} aria-hidden="true"/>{t('Back to account access','অ্যাকাউন্টে ফিরুন')}</Link>
          <Link href={adminPath(locale === 'en' ? 'bn' : 'en', destination)}>{locale === 'en' ? 'বাংলা' : 'English'}</Link>
        </div>
        <h1 id="admin-sign-in">{t('Admin sign in','অ্যাডমিন সাইন ইন')}</h1>
        <p>{accountIsRegular
          ? t('Your current account has regular access. Sign in with an administrator account to continue.','আপনার বর্তমান অ্যাকাউন্টে সাধারণ অ্যাক্সেস আছে। চালিয়ে যেতে অ্যাডমিন অ্যাকাউন্টে সাইন ইন করুন।')
          : t('Use your provisioned administrator account.','আপনার জন্য বরাদ্দ অ্যাডমিন অ্যাকাউন্ট ব্যবহার করুন।')}</p>
        {FRONTEND_PREVIEW ? <p role="status">{t('Connect the AgroSphere API to use admin sign-in.','অ্যাডমিন সাইন ইনের জন্য এপিআই সংযোগ দিন।')}</p>
          : <form className={styles.loginForm} onSubmit={submit} aria-busy={busy}>
            <label>{t('Admin email','অ্যাডমিন ইমেইল')}
              <input type="email" name="email" autoComplete="username" autoCapitalize="none" maxLength={254} required disabled={busy}/>
            </label>
            <label>{t('Password','পাসওয়ার্ড')}
              <input name="password" type="password" autoComplete="current-password" maxLength={1024} required disabled={busy}/>
            </label>
            {error && <p role="alert" className={styles.signError}>{error}</p>}
            <button className={styles.primary} disabled={busy}>
              {busy ? t('Signing in…','সাইন ইন হচ্ছে…') : t('Sign in as admin','অ্যাডমিন হিসেবে প্রবেশ করুন')}
              <ArrowRight size={17} aria-hidden="true"/>
            </button>
          </form>}
      </section>
    </div>
  </main>;
}

function AdminWorkspace({current, locale, t, userId, name}: {
  current: SectionEntry; locale: Locale; t: Text; userId: string; name: string;
}) {
  const {signOut, refreshSession} = useSession();
  const queryClient = useQueryClient();
  const router = useRouter();
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{error: boolean; message: string} | null>(null);

  async function perform(work: () => Promise<unknown>, success = t('Changes saved.','পরিবর্তন সংরক্ষিত হয়েছে।')) {
    if (pending.current) return false;
    pending.current = true;
    setBusy(true);
    setFeedback(null);
    try {
      await work();
      setFeedback({error:false, message:success});
      await queryClient.invalidateQueries({queryKey: ['market', userId]});
      return true;
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) void refreshSession();
      setFeedback({error:true, message:error instanceof Error ? error.message : t('Could not save changes.','পরিবর্তন সংরক্ষণ করা যায়নি।')});
      return false;
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <MarketContext.Provider value={{locale, t, userId, role:'admin', busy, perform,
    go: path => router.push('/' + locale + '/marketplace/' + path)}}>
    <div className={styles.shell} lang={locale}>
      <aside className={styles.rail}>
        <Link href={adminPath(locale)} className={styles.brand}><Sprout size={22} aria-hidden="true"/> AgroSphere AI</Link>
        <nav className={styles.navigation} aria-label={t('Admin sections','অ্যাডমিন বিভাগ')}>
          {groups.map(group => <div className={styles.navGroup} key={group.label[0]}>
            <span>{t(group.label[0], group.label[1])}</span>
            {group.items.map(item => <Link key={item.id} href={adminPath(locale, item.id)}
              aria-current={current.id === item.id ? 'page' : undefined}>
              <item.icon size={17} aria-hidden="true"/>{t(...item.name)}
            </Link>)}
          </div>)}
        </nav>
      </aside>
      <div className={styles.body}>
        <header className={styles.topbar}>
          <span className={styles.topTitle}><ShieldCheck size={17} aria-hidden="true"/>{t('Admin console','অ্যাডমিন কনসোল')}</span>
          <div className={styles.topActions}>
            <span className={styles.operator} title={name}>{name}</span>
            <Link href={adminPath(locale === 'en' ? 'bn' : 'en', current.id)}>{locale === 'en' ? 'বাংলা' : 'English'}</Link>
            <button type="button" onClick={() => void signOut()}>
              <LogOut size={15} aria-hidden="true"/>{t('Sign out','বের হন')}
            </button>
          </div>
        </header>
        <main className={styles.main + ' mk-root'}>
          <div className={styles.heading}>
            <h1>{t(...current.name)}</h1>
            <p>{t(...current.description)}</p>
          </div>
          {feedback && <p role={feedback.error ? 'alert' : 'status'} className={feedback.error ? 'mk-error' : 'mk-success'}>
            {feedback.message}
          </p>}
          {current.id === 'overview' || current.id === 'activity' ? <PlatformOverview activityOnly={current.id === 'activity'}/>
            : current.id === 'system' ? <SystemStatus/>
            : current.id === 'policy' ? <AdminPolicy/>
            : <AdminList key={current.id} kind={current.id}/>}
        </main>
      </div>
    </div>
  </MarketContext.Provider>;
}

function PlatformOverview({activityOnly}: {activityOnly: boolean}) {
  const {locale, t} = useMarket();
  const query = useMarketQuery<OverviewData>('/admin/overview');
  const data = query.data;
  const format = new Intl.NumberFormat(locale === 'bn' ? 'bn-BD' : 'en-BD');
  if (!data) return <DataState query={query}/>;
  const metrics: [string, string, number, Section, LucideIcon][] = [
    ['Accounts','অ্যাকাউন্ট',data.accounts.total,'users',Users],
    ['Registered farms','নিবন্ধিত খামার',data.records.farm,'activity',Sprout],
    ['Listings','পণ্য তালিকা',data.marketplace.listings,'products',Package],
    ['Open reports','খোলা রিপোর্ট',data.marketplace.open_reports,'reports',Bell],
  ];
  return <>
    <DataState query={query}/>
    <div className={styles.snapshot}><span>{t('Updated','হালনাগাদ')} {formatTime(data.generated_at, locale)}</span>
      <button disabled={query.isFetching} onClick={() => void query.refetch()}>{t('Refresh','হালনাগাদ করুন')}</button></div>
    {!activityOnly && <>
      <div className={styles.metrics}>{metrics.map(([english, bangla, value, path, Icon]) =>
        <Link key={path} href={adminPath(locale, path)} className={styles.metric}>
          <span className={styles.metricIcon}><Icon size={19} aria-hidden="true"/></span>
          <ArrowRight size={16} aria-hidden="true" className={styles.metricArrow}/>
          <span>{t(english,bangla)}</span>
          <strong>{format.format(value)}</strong>
        </Link>)}</div>
      <div className={styles.summaryGrid}>
        <section className={styles.sheet}>
          <h2>{t('Account breakdown','অ্যাকাউন্টের হিসাব')}</h2>
          <dl className={styles.numbers}>
            <dt>{t('Farmers','কৃষক')}</dt><dd>{format.format(data.accounts.farmer)}</dd>
            <dt>{t('Customers','ক্রেতা')}</dt><dd>{format.format(data.accounts.customer)}</dd>
            <dt>{t('Administrators','অ্যাডমিন')}</dt><dd>{format.format(data.accounts.admin)}</dd>
            <dt>{t('Active accounts','সক্রিয় অ্যাকাউন্ট')}</dt><dd>{format.format(data.accounts.active)}</dd>
            <dt>{t('Demo accounts','ডেমো অ্যাকাউন্ট')}</dt><dd>{format.format(data.accounts.demo)}</dd>
          </dl>
        </section>
        <section className={styles.sheet}>
          <h2>{t('Marketplace operations','বাজারের কার্যক্রম')}</h2>
          <dl className={styles.numbers}>
            <dt>{t('Purchases and bidding','কেনাকাটা ও বিড')}</dt><dd>{data.marketplace.enabled ? t('Enabled','চালু') : t('Paused','বন্ধ')}</dd>
            <dt>{t('Orders','অর্ডার')}</dt><dd>{format.format(data.marketplace.orders)}</dd>
            <dt>{t('Auctions','নিলাম')}</dt><dd>{format.format(data.marketplace.auctions)}</dd>
            <dt>{t('Open reports','খোলা রিপোর্ট')}</dt><dd>{format.format(data.marketplace.open_reports)}</dd>
          </dl>
        </section>
      </div>
    </>}
    <section className={styles.sheet}>
      <h2>{t(activityOnly ? 'Records by feature' : 'Farm tools at a glance', activityOnly ? 'ফিচার অনুযায়ী রেকর্ড' : 'খামারের টুল এক নজরে')}</h2>
      <p>{t('Counts include demo records.','হিসাবে ডেমো রেকর্ডও আছে।')}</p>
      <ul className={styles.activity}>{(activityOnly ? activity : activity.slice(0, 6)).map(([key, english, bangla, Icon]) =>
        <li key={key}><Icon size={17} aria-hidden="true"/><span>{t(english,bangla)}</span><strong>{format.format(data.records[key] ?? 0)}</strong></li>)}</ul>
      {!activityOnly && <Link className={styles.textLink} href={adminPath(locale, 'activity')}>{t('View all farm activity','সব খামারের কার্যক্রম দেখুন')} <ArrowRight size={16} aria-hidden="true"/></Link>}
    </section>
  </>;
}

function SystemStatus() {
  const {t} = useMarket();
  const query = useMarketQuery<SystemData>('/admin/system');
  const data = query.data;
  if (!data) return <DataState query={query}/>;
  return <>
    <DataState query={query}/>
    <section className={styles.sheet}>
      <h2>{t('Platform configuration','প্ল্যাটফর্ম কনফিগারেশন')}</h2>
      <dl className={styles.numbers}>
        <dt>{t('Data mode','ডেটা মোড')}</dt><dd>{data.data_mode}</dd>
        <dt>{t('Farmer Chat provider','কৃষি সহায়কের প্রোভাইডার')}</dt>
        <dd>{data.chat_configured ? t('Configured','কনফিগার করা আছে') : t('Published guidance only','শুধু প্রকাশিত নির্দেশিকা')}</dd>
      </dl>
    </section>
    <section className={styles.sheet}>
      <h2>{t('AgroDoctor model files','এগ্রোডক্টরের মডেল ফাইল')}</h2>
      <ul className={styles.activity}>{data.models.map(model => <li key={model.model_id}>
        <ScanLine size={17} aria-hidden="true"/><span>{model.model_id} · {model.version}</span>
        <strong>{model.available ? t('Available','প্রস্তুত')
          : model.artifact_status === 'broken_artifact' ? t('Invalid model file','মডেল ফাইল অকার্যকর')
          : t('Unavailable','অনুপলব্ধ')}</strong>
      </li>)}</ul>
    </section>
  </>;
}
