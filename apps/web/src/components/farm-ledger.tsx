'use client';

import {useState} from 'react';
import Link from 'next/link';
import {useQuery} from '@tanstack/react-query';
import {request} from '@/lib/api';
import {day, expenses, fields, number, type FarmToolData, type Locale, type Localize, type Write} from './farm-tools-data';

export function FarmLedger({data, base, locale, t, write, busy}: {
  data:FarmToolData; base:string; locale:Locale; t:Localize; write:Write; busy:boolean;
}) {
  const [kind, setKind] = useState('expense');
  const [weight, setWeight] = useState('');
  const [quote, setQuote] = useState('');
  const quoteQuery = useQuery({
    queryKey:['farm-break-even',base,quote,data.summary.expenses_bdt],
    queryFn:({signal})=>request<FarmToolData>(base + '?break_even_kg=' + encodeURIComponent(quote),{signal}),
    enabled:!!quote,
  });
  const money = (amount:string) => '৳' + number(amount,locale,2);
  return <>
    <section className="panel">
      <h2>{t('Plot cash ledger','জমির আয়-ব্যয়ের খাতা')}</h2>
      <p>{t('Cash margin uses the receipts and expenses entered for this plot. Add produce sales after you receive payment.',
        'এই জমির লেখা আয় ও ব্যয় দিয়ে নগদ লাভ বা ক্ষতি হিসাব করা হয়। টাকা পাওয়ার পরে ফসল বিক্রির আয় লিখুন।')}</p>
      <dl className="farm-tool-totals">
        <div><dt>{t('Receipts','আয়')}</dt><dd>{money(data.summary.receipts_bdt)}</dd></div>
        <div><dt>{t('Expenses','ব্যয়')}</dt><dd>{money(data.summary.expenses_bdt)}</dd></div>
        <div><dt>{t('Cash margin','নগদ লাভ বা ক্ষতি')}</dt><dd>{money(data.summary.margin_bdt)}</dd></div>
      </dl>
      <form onSubmit={event=>{
        event.preventDefault();
        const form=event.currentTarget;
        const values=fields(form);
        void write(base+'/ledger','POST',{...values,kind,category:kind==='receipt'?'sale':values.category})
          .then(ok=>{if(ok)form.reset();});
      }}>
        <div className="form-grid">
          <label>{t('Entry type','হিসাবের ধরন')}<select value={kind} onChange={e=>setKind(e.target.value)}>
            <option value="expense">{t('Expense','ব্যয়')}</option><option value="receipt">{t('Sale or other receipt','বিক্রি বা অন্যান্য আয়')}</option>
          </select></label>
          {kind==='expense'&&<label>{t('Category','খাত')}<select name="category">{expenses.map(([id,en,bn])=><option key={id} value={id}>{t(en,bn)}</option>)}</select></label>}
          <label>{t('Description','বিবরণ')}<input name="label" required maxLength={100}/></label>
          <label>{t('Amount in BDT','টাকায় পরিমাণ')}<input name="amount_bdt" type="number" required min=".01" step=".01" max="1000000000"/></label>
          <label>{t('Entry date','হিসাবের তারিখ')}<input name="date" type="date" required defaultValue={data.today} max={data.today}/></label>
        </div>
        <button className="btn primary" disabled={busy}>{t('Save entry','হিসাব সংরক্ষণ করুন')}</button>
      </form>
    </section>
    <section className="panel">
      <h3>{t('Break-even selling price','খরচ ওঠানোর বিক্রয়মূল্য')}</h3>
      <p>{t('Divide recorded expenses by the weight you expect to sell. Add selling costs to the ledger if they have already been paid.',
        'যত কেজি বিক্রি করতে চান তা দিয়ে লিখিত ব্যয় ভাগ করুন। বিক্রির খরচ হয়ে থাকলে খাতায় যোগ করুন।')}</p>
      <form className="farm-tool-inline" onSubmit={e=>{e.preventDefault();setQuote(weight);}}>
        <label>{t('Expected sale weight (kg)','বিক্রির সম্ভাব্য ওজন (কেজি)')}
          <input required type="number" step=".001" min=".001" max="1000000" value={weight} onChange={e=>{setWeight(e.target.value);setQuote('');}}/>
        </label>
        <button className="btn secondary">{t('Calculate','হিসাব করুন')}</button>
      </form>
      {quoteQuery.isFetching&&quote&&<p role="status">{t('Calculating…','হিসাব হচ্ছে…')}</p>}
      {quoteQuery.isError&&quote&&<p className="error" role="alert">{quoteQuery.error.message} <button type="button" className="text-link" onClick={()=>void quoteQuery.refetch()}>{t('Retry','আবার চেষ্টা করুন')}</button></p>}
      {quote&&quoteQuery.data&&<p role="status"><strong>{quoteQuery.data.summary.break_even_bdt_per_kg
        ? money(quoteQuery.data.summary.break_even_bdt_per_kg) + t(' per kg',' প্রতি কেজি')
        : t('Record expenses to calculate a price.','মূল্য হিসাব করতে ব্যয় লিখুন।')}</strong></p>}
      <Link className="text-link" href={`/${locale}/market`}>{t('Compare prices in KrishiMarket','কৃষিমার্কেটে দাম তুলনা করুন')}</Link>
    </section>
    <section className="panel">
      <h3>{t('Recorded entries','সংরক্ষিত হিসাব')}</h3>
      {!data.ledger.length&&<p>{t('This plot has no entries yet.','এই জমিতে এখনো কোনো হিসাব নেই।')}</p>}
      <ul className="farm-tool-list">{data.ledger.map(row=><li key={row.id}>
        <span><strong>{row.label}</strong><small>{day(row.date,locale)} · {row.kind==='expense'?t('Expense','ব্যয়'):t('Receipt','আয়')}</small></span>
        <strong>{row.kind==='expense'?'−':'+'}{money(row.amount_bdt)}</strong>
        <button type="button" className="text-link" disabled={busy} onClick={()=>{
          if(window.confirm(t('Delete this ledger entry?','এই হিসাব মুছবেন?')))void write('/farm-tools/records/farm_ledger/'+row.id,'DELETE');
        }}>{t('Delete','মুছুন')}</button>
      </li>)}</ul>
    </section>
  </>;
}
