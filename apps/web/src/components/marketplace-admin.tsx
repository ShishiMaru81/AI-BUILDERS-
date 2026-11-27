'use client';
import {useState,type FormEvent} from 'react';
import {Search} from 'lucide-react';
import type {Auction,Order,PageOf,Product} from '@/lib/marketplace-types';
import {useMarket,useMarketQuery,send,rows,Field,Panel,DataState,cash,Empty} from './marketplace-shared';
import {AuctionBox} from './marketplace-commerce';

type AdminUser={id:string;name:string;email?:string;role:string;is_active:boolean;verification_status?:string};
type Report={id:string;product_id?:string;order_id?:string;reason:string;details?:string;status:string;admin_note?:string;created_at:string};
type Audit={id:string;actor_id:string;event:string;entity_type:string;entity_id:string;details:unknown;created_at:string};
type Policy={marketplace_enabled:boolean;require_verified_farmer:boolean;max_bids_per_minute:number;winner_confirmation_hours:number;order_acceptance_hours:number};
export type AdminListKind = 'users' | 'products' | 'reports' | 'orders' | 'auctions' | 'audit';

export function AdminList({kind}: {kind: AdminListKind}) {
  const {t, locale} = useMarket();
  const [{offset, search}, setFilter] = useState({offset: 0, search: ''});
  const [input, setInput] = useState('');
  const pagination = new URLSearchParams({offset: String(offset), limit: '20', search});
  const query = useMarketQuery<PageOf<AdminUser | Product | Report | Order | Auction | Audit>>(
    '/admin/market/' + kind + '?' + pagination,
  );
  const items = rows(query.data);
  const format = new Intl.NumberFormat(locale === 'bn' ? 'bn-BD' : 'en-BD');
  return <>
    <form className="admin-collection-search" role="search" onSubmit={event => {
      event.preventDefault();
      setFilter({search: input.trim(), offset: 0});
    }}>
      <label><Search size={17} aria-hidden="true"/>
        <input type="search" name="search" aria-label={t('Search records', 'রেকর্ড খুঁজুন')}
          placeholder={t('Search this section', 'এই বিভাগে খুঁজুন')} maxLength={100}
          value={input} onChange={event => setInput(event.target.value)}/>
      </label>
      <button type="submit">{t('Search', 'খুঁজুন')}</button>
      {search && <button type="button" onClick={() => {
        setInput('');
        setFilter({search: '', offset: 0});
      }}>{t('Clear', 'মুছুন')}</button>}
    </form>
    <DataState query={query}/>
    {query.data && <div className="admin-collection-list">
      {items.map(row => {
        const title = 'name' in row ? row.name : 'reason' in row ? row.reason
          : 'event' in row ? row.event.replaceAll('.', ' · ') : row.id;
        const status = 'verification_status' in row && 'is_active' in row
          ? (row.is_active ? t('Active','সক্রিয়') : t('Suspended','স্থগিত'))
          : 'status' in row ? row.status : 'state' in row ? row.state : '';
        return <details key={row.id} className="admin-collection-record">
          <summary><span>{title}</span>{status && <span className="mk-badge">{status}</span>}</summary>
          {kind === 'users' ? <UserReview user={row as AdminUser}/>
            : kind === 'products' ? <ProductModeration product={row as Product}/>
            : kind === 'reports' ? <ReportResolution key={(row as Report).status} report={row as Report}/>
            : kind === 'auctions' ? <AdminAuction auction={row as Auction}/>
            : kind === 'orders' ? <AdminOrder order={row as Order}/>
            : <AuditRow audit={row as Audit}/>}
        </details>;
      })}
      {!items.length && <Empty>{t('No matching records.', 'মিল আছে এমন রেকর্ড নেই।')}</Empty>}
      {(offset > 0 || query.data.has_more) && <div className="mk-row mk-pagination">
        <button disabled={!offset || query.isFetching} onClick={() => setFilter({search, offset: offset - 20})}>
          {t('Previous', 'আগের')}
        </button>
        <span>{format.format(items.length ? offset + 1 : 0)}–{format.format(items.length ? offset + items.length : 0)}
          {' / '}{format.format(query.data.total)}</span>
        <button disabled={!query.data.has_more || query.isFetching} onClick={() => setFilter({search, offset: offset + 20})}>
          {t('Next', 'পরের')}
        </button>
      </div>}
    </div>}
  </>;
}
function UserReview({user:u}:{user:AdminUser}){const {t,perform,busy,userId}=useMarket();return <Panel><h2>{u.name}</h2><p>{u.email} · {u.role} · {u.is_active?t('Active','সক্রিয়'):t('Suspended','স্থগিত')}</p><form onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void perform(()=>send('/admin/market/users/'+u.id,{is_active:f.get('is_active')==='true',reason:f.get('reason')},'PATCH'));}}><div className="mk-grid"><Field label={t('Account status','অ্যাকাউন্টের অবস্থা')}><select name="is_active" defaultValue={String(u.is_active)} disabled={u.id===userId}><option value="true">{t('Active','সক্রিয়')}</option><option value="false">{t('Suspended','স্থগিত')}</option></select></Field></div><Field label={t('Administrative reason','প্রশাসনিক কারণ')}><input name="reason" required minLength={3} maxLength={1000}/></Field><button disabled={busy||u.id===userId}>{t('Save user review','ব্যবহারকারীর পর্যালোচনা সংরক্ষণ')}</button></form>{(u.role==='farmer'||u.role==='customer')&&<form className="mk-inset" onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void perform(()=>send('/admin/market/farmers/'+u.id,{verification_status:f.get('verification_status'),reason:f.get('reason')},'PATCH'));}}><Field label={t('Seller verification','বিক্রেতা যাচাই')}><select name="verification_status" defaultValue={u.verification_status||'unverified'}>{['unverified','pending','verified','rejected'].map(v=><option key={v}>{v}</option>)}</select></Field><Field label={t('Verification reason','যাচাইয়ের কারণ')}><input name="reason" required minLength={3} maxLength={1000}/></Field><button disabled={busy}>{t('Save seller verification','বিক্রেতা যাচাই সংরক্ষণ')}</button></form>}</Panel>;}
function ProductModeration({product:p}:{product:Product}){const {t,busy,perform}=useMarket();return <Panel><h2>{p.name}</h2><p>{p.seller_name} · {p.district} · {cash(p.price_bdt)} / {p.unit} · {p.status} · {p.moderation_status}</p><p>{p.description}</p><form onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void perform(()=>send('/admin/market/products/'+p.id,{moderation_status:f.get('moderation_status'),reason:f.get('reason')},'PATCH'));}}><Field label={t('Moderation decision','মডারেশনের সিদ্ধান্ত')}><select name="moderation_status" defaultValue={p.moderation_status==='hidden'?'hidden':'visible'}><option value="visible">{t('Approved / visible','অনুমোদিত / দৃশ্যমান')}</option><option value="hidden">{t('Hidden from marketplace','বাজার থেকে লুকানো')}</option></select></Field><Field label={t('Moderation reason','মডারেশনের কারণ')}><input name="reason" required minLength={3} maxLength={1000}/></Field><button disabled={busy}>{t('Save moderation','মডারেশন সংরক্ষণ')}</button></form></Panel>;}
function ReportResolution({report:r}:{report:Report}){const {t,busy,perform}=useMarket();return <Panel><h2>{t('Report','রিপোর্ট')} {r.id.slice(0,8)}</h2><p>{r.reason}</p><p>{r.details}</p><small>{r.product_id||r.order_id} · {r.created_at}</small><form onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void perform(()=>send('/admin/market/reports/'+r.id,{status:f.get('status'),admin_note:f.get('admin_note')},'PATCH'));}}><Field label={t('Report status','রিপোর্টের অবস্থা')}><select name="status" required defaultValue={r.status==='open'?'':r.status}><option value="" disabled>{t('Open · Select a decision','খোলা · সিদ্ধান্ত বেছে নিন')}</option><option value="dismissed">{t('Dismissed','খারিজ')}</option><option value="resolved">{t('Resolved','সমাধান হয়েছে')}</option></select></Field><Field label={t('Resolution note','সমাধানের নোট')}><textarea name="admin_note" required minLength={3} maxLength={1000} defaultValue={r.admin_note}/></Field><button disabled={busy}>{t('Save report review','রিপোর্ট পর্যালোচনা সংরক্ষণ')}</button></form></Panel>;}
function AdminAuction({auction:a}:{auction:Auction}){const {t,busy,perform}=useMarket();return <><AuctionBox auction={a}/>{['draft','scheduled','live','active','awarded'].includes(a.state)&&<form className="mk-inset" onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void perform(()=>send('/market/auctions/'+a.id+'/cancel',{reason:f.get('reason')}));}}><Field label={t('Auction intervention reason','নিলামে হস্তক্ষেপের কারণ')}><input name="reason" required minLength={3} maxLength={1000}/></Field><button disabled={busy}>{t('Cancel auction and release lot','নিলাম বাতিল ও লট মুক্ত করুন')}</button></form>}</>;}
function AdminOrder({order:o}:{order:Order}){const {t,perform,busy}=useMarket();return <Panel><h2>{t('Order','অর্ডার')} {o.id}</h2><p>{o.status} · {o.payment_status} · {cash(o.total_bdt)}</p>{o.seller_orders.map(s=><div className="mk-seller-group" key={s.id}><h3>{s.fulfillment} · {s.status}</h3>{s.items.map(i=><p key={i.product_id}>{i.name} · {i.quantity} {i.unit} · {cash(i.line_total_bdt)}</p>)}<p>{s.destination?.name} · {s.destination?.district}</p>{['pending','confirmed','preparing','ready_for_pickup'].includes(s.status)&&<form onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void perform(()=>send('/market/seller-orders/'+s.id,{status:f.get('status'),reason:f.get('reason'),cash_received:false},'PATCH'));}}><Field label={t('Order intervention','অর্ডারে হস্তক্ষেপ')}><select name="status"><option value="cancelled">{t('Cancel and release stock','বাতিল ও মজুত মুক্ত করুন')}</option></select></Field><Field label={t('Order intervention reason','অর্ডারে হস্তক্ষেপের কারণ')}><input required name="reason" minLength={3} maxLength={1000}/></Field><button disabled={busy}>{t('Apply order intervention','অর্ডারে পদক্ষেপ নিন')}</button></form>}</div>)}</Panel>;}
function AuditRow({audit:a}:{audit:Audit}){return <Panel><h2>{a.event}</h2><p>{a.created_at} · {a.actor_id||'System'}</p><p>{a.entity_type}: {a.entity_id}</p><pre className="mk-audit">{JSON.stringify(a.details,null,2)}</pre></Panel>;}
export function AdminPolicy(){const {t,perform,busy}=useMarket();const q=useMarketQuery<Policy>('/admin/market/policy');async function save(e:FormEvent<HTMLFormElement>){e.preventDefault();const f=new FormData(e.currentTarget);const body={marketplace_enabled:f.get('marketplace_enabled')==='on',require_verified_farmer:f.get('require_verified_farmer')==='on',max_bids_per_minute:Number(f.get('max_bids_per_minute')),winner_confirmation_hours:Number(f.get('winner_confirmation_hours')),order_acceptance_hours:Number(f.get('order_acceptance_hours'))};await perform(()=>send('/admin/market/policy',body,'PATCH'));}return <><DataState query={q}/>{q.data&&<Panel title={t('Marketplace policy','বাজারের নীতিমালা')}><form onSubmit={save}><label className="mk-check"><input type="checkbox" name="marketplace_enabled" defaultChecked={q.data.marketplace_enabled}/>{t('Enable marketplace purchases and bids','বাজারের কেনাকাটা ও বিড চালু করুন')}</label><label className="mk-check"><input type="checkbox" name="require_verified_farmer" defaultChecked={q.data.require_verified_farmer}/>{t('Require farmer verification for published listings','প্রকাশিত পণ্যের জন্য কৃষক যাচাই বাধ্যতামূলক')}</label><div className="mk-grid mk-three">{[['max_bids_per_minute','Bids per minute','প্রতি মিনিটে বিড',60],['winner_confirmation_hours','Winner confirmation hours','জেতার পরে নিশ্চিত করার ঘণ্টা',72],['order_acceptance_hours','Order acceptance hours','অর্ডার গ্রহণের ঘণ্টা',168]].map(([key,en,bn,max])=><Field key={key} label={t(String(en),String(bn))}><input type="number" name={String(key)} min="1" max={Number(max)} step="1" required defaultValue={q.data![key as keyof Policy] as number}/></Field>)}</div><button className="mk-primary" disabled={busy}>{t('Save policy','নীতিমালা সংরক্ষণ')}</button></form></Panel>}</>;}
