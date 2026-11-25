export type Locale = 'en' | 'bn';
export type Localize = (en: string, bn: string) => string;
export type Write = (path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: unknown) => Promise<boolean>;
export type Line = {id:string; kind:'expense'|'receipt'; category:string; amount_bdt:string; date:string; label:string};
export type BatchEvent = {id:string; kind:'inspection'|'loss'|'removed'; date:string; label:string; quantity_kg:string|null};
export type Batch = {
  id:string; label:string; crop:string; harvested_on:string; stored_on:string; method:string; quantity_kg:string;
  remaining_kg:number; loss_kg:number; loss_pct:number; events:BatchEvent[];
};
export type FarmToolData = {
  today:string; plot_name:string; planting_date:string|null;
  calendar:{
    crop:string; district:string|null; stage:string|null; region:string|null; planting_week:number|null; week_start:string;
    source_url:string|null; tasks:{date:string; en:string; bn:string}[];
  };
  alerts:{id:string; kind:'rain'|'scout'; en:string; bn:string; detail?:string; hours?:number; source_url?:string}[];
  reminders:{id:string; label:string; due_on:string}[];
  ledger:Line[];
  summary:{expenses_bdt:string; receipts_bdt:string; margin_bdt:string; break_even_bdt_per_kg:string|null};
  storage:Batch[]; sharing_allowed:boolean; shared_case_ids:string[];
};

export const stages = [
  ['Seedling','চারা'], ['Vegetative','পাতা বৃদ্ধি'], ['Flowering','ফুল'], ['Fruiting','ফল বা কন্দ বৃদ্ধি'], ['Harvest','ফসল তোলা'],
];
export const expenses = [
  ['seed','Seed','বীজ'], ['inputs','Inputs','উপকরণ'], ['labour','Labour','শ্রম'],
  ['transport','Transport','পরিবহন'], ['storage','Storage','সংরক্ষণ'], ['other','Other','অন্যান্য'],
];
export const methods = [
  ['ambient','Room temperature','ঘরের তাপমাত্রা'], ['ventilated','Ventilated','বায়ু চলাচলের ব্যবস্থা'],
  ['cold','Cold storage','হিমাগার'], ['other','Other','অন্যান্য'],
];
export const movements = [
  ['inspection','Inspection','পরিদর্শন'], ['loss','Loss','ক্ষতি'], ['removed','Removed or sold','সরানো বা বিক্রি'],
];

export function fields(form: HTMLFormElement) {
  return Object.fromEntries(new FormData(form)) as Record<string, string>;
}

export function number(value: number|string, locale: Locale, fraction = 3) {
  return new Intl.NumberFormat(locale === 'bn' ? 'bn-BD' : 'en-BD', {maximumFractionDigits:fraction}).format(Number(value));
}

export function day(value: string, locale: Locale) {
  const parsed = new Date(value + 'T00:00:00Z');
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat(locale === 'bn' ? 'bn-BD' : 'en-BD', {
    month:'short', day:'numeric', year:'numeric', timeZone:'UTC',
  }).format(parsed);
}
