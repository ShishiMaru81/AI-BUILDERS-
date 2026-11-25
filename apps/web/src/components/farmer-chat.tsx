'use client';

import {useEffect, useRef, useState} from 'react';
import {usePathname} from 'next/navigation';
import {useQueryClient} from '@tanstack/react-query';
import {ArrowRight, ArrowUp, ArrowUpRight, BookOpen, Check, ChevronLeft, CloudRain, Copy, FileText, History, Leaf, LoaderCircle, MapPin, MessageCircle, NotebookPen, Phone, ScanLine, ShoppingBasket, Sprout, SquarePen, X} from 'lucide-react';
import {ApiError, request} from '@/lib/api';
import {ChatDictation, ReadChatReply} from './chat-speech';
import styles from './farmer-chat.module.css';

type Locale = 'en' | 'bn';
type ChatProps = {locale: Locale; userId: string; plotId?: string; caseId?: string; plotName?: string};
type OpenContext = {caseId?: string; plotId?: string; draft?: string};
type Action = {kind: 'navigate' | 'call' | 'note' | 'handoff'; label: string; target: string; done?: boolean};
type Message = {
  id: string; role: 'user' | 'assistant'; text: string;
  sources?: {label: string; url?: string; detail?: string}[];
  actions?: Action[]; mode?: 'groq' | 'tool' | 'limited';
};
type Conversation = {conversation_id: string; messages: Message[]};
type Index = {active: string | null; entries: {id: string; date: number}[]};
type Operation = {kind: 'load'; id: string} | {kind: 'send'; text: string; id: string} | {kind: 'note'; id: string};

const labels = {
  en: {
    title: 'Farmer chat', close: 'Close chat', new: 'New chat', history: 'Previous chats', back: 'Back to chat',
    farm: 'AgroSphere AI', screening: 'Saved screening', welcome: 'How can I help on your farm?',
    explain: 'What does this result mean?', next: 'What should I check next?', adviser: 'Help me prepare a message for an adviser.',
    plant: 'What should I check on my crop?', rain: 'How should I prepare for rain?', market: 'What prices are recorded for my crop?',
    input: 'Your question', placeholder: 'Ask about your farm…', send: 'Send message', retry: 'Retry',
    loading: 'Opening your conversation…', sending: 'Preparing a reply…', saving: 'Saving note…',
    failed: 'Your question couldn’t be sent. You can edit it or retry.', loadFailed: 'Your conversation couldn’t be opened.',
    noteFailed: 'The note couldn’t be saved.', expired: 'Your session has expired. Sign in again.',
    rated: 'The chat is busy. Please try again shortly.', tooLong: 'Keep your question to 1,600 characters.',
    conflict: 'Reopen this conversation from Previous chats to see the latest replies. If the conversation is full, start a new chat.',
    you: 'You', groq: 'AI reply', tool: 'From farm tools', limited: 'Limited guidance',
    sources: 'Sources', saved: 'Note saved', handoff: 'Handoff text', copy: 'Copy text', copied: 'Copied',
    manualCopy: 'Text selected. Use your device’s Copy command.', previous: 'Conversation', noHistory: 'Your conversations will appear here.',
    listLoading: 'Checking for previous chats…', listFailed: 'Couldn’t refresh previous chats.',
  },
  bn: {
    title: 'কৃষি সহায়ক', close: 'চ্যাট বন্ধ করুন', new: 'নতুন চ্যাট', history: 'আগের চ্যাট', back: 'চ্যাটে ফিরুন',
    farm: 'এগ্রোস্ফিয়ার AI', screening: 'সংরক্ষিত পরীক্ষার ফল', welcome: 'খামারের কী নিয়ে জানতে চান?',
    explain: 'এই ফলাফলের মানে কী?', next: 'এরপর কী পরীক্ষা করব?', adviser: 'কৃষি কর্মকর্তাকে কী লিখব?',
    plant: 'ফসলে কী কী লক্ষণ দেখব?', rain: 'বৃষ্টির আগে কী প্রস্তুতি নেব?', market: 'আমার ফসলের কী দাম নথিভুক্ত আছে?',
    input: 'আপনার প্রশ্ন', placeholder: 'খামার নিয়ে প্রশ্ন করুন…', send: 'প্রশ্ন পাঠান', retry: 'আবার চেষ্টা করুন',
    loading: 'আগের চ্যাট খোলা হচ্ছে…', sending: 'উত্তর তৈরি হচ্ছে…', saving: 'নোট সংরক্ষণ হচ্ছে…',
    failed: 'প্রশ্নটি পাঠানো যায়নি। চাইলে বদলে আবার পাঠান।', loadFailed: 'আগের চ্যাট খোলা যায়নি।',
    noteFailed: 'নোট সংরক্ষণ করা যায়নি।', expired: 'সেশন শেষ হয়েছে। আবার সাইন ইন করুন।',
    rated: 'চ্যাট এখন ব্যস্ত। একটু পরে আবার চেষ্টা করুন।', tooLong: 'প্রশ্নটি ১,৬০০ অক্ষরের মধ্যে লিখুন।',
    conflict: 'সাম্প্রতিক উত্তর দেখতে আগের চ্যাট থেকে কথোপকথনটি আবার খুলুন। চ্যাট পূর্ণ হলে নতুন চ্যাট শুরু করুন।',
    you: 'আপনি', groq: 'এআইয়ের উত্তর', tool: 'খামারের তথ্য থেকে', limited: 'সীমিত পরামর্শ',
    sources: 'তথ্যসূত্র', saved: 'নোট সংরক্ষিত', handoff: 'কর্মকর্তার জন্য বার্তা', copy: 'লেখা কপি করুন', copied: 'কপি হয়েছে',
    manualCopy: 'লেখা নির্বাচন করা হয়েছে। ডিভাইসের কপি অপশন ব্যবহার করুন।', previous: 'কথোপকথন', noHistory: 'আপনার আগের চ্যাট এখানে দেখা যাবে।',
    listLoading: 'আগের চ্যাট খোঁজা হচ্ছে…', listFailed: 'আগের চ্যাটের তালিকা আনা যায়নি।',
  },
};
type Labels = typeof labels.en;

function readIndex(key: string): Index {
  try {
    const value = JSON.parse(localStorage.getItem(key) || 'null');
    if (Array.isArray(value?.entries)) {
      const entries = value.entries.filter((entry: Index['entries'][number]) => typeof entry?.id === 'string' && Number.isFinite(entry.date));
      return {entries, active: entries.some((entry: Index['entries'][number]) => entry.id === value.active) ? value.active : null};
    }
  } catch { /* Chat also works when browser storage is unavailable. */ }
  return {active: null, entries: []};
}

function newRequestId() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  // Browsers on a local HTTP network still expose getRandomValues.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
}

function ChatMark() {
  return <span className={styles.mark} aria-hidden="true"><MessageCircle size={33} strokeWidth={1.45}/><Sprout size={18} strokeWidth={1.9}/></span>;
}

function Handoff({action, t}: {action: Action; t: Labels}) {
  const [text, setText] = useState(action.target);
  const [status, setStatus] = useState('');
  const editor = useRef<HTMLTextAreaElement>(null);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setStatus(t.copied);
    } catch {
      editor.current?.focus();
      editor.current?.select();
      setStatus(t.manualCopy);
    }
  }
  return <details className={styles.handoff}>
    <summary><FileText size={15}/>{action.label}</summary>
    <textarea ref={editor} aria-label={t.handoff} value={text} rows={3} onChange={e => {setText(e.target.value); setStatus('');}}/>
    <button type="button" onClick={copy} disabled={!text.trim()}><Copy size={14}/>{t.copy}</button>
    <small role="status">{status}</small>
  </details>;
}

function Reply({message, locale, busy, visible, onNote}: {
  message: Message; locale: Locale; busy: boolean; visible: boolean; onNote: (id: string) => void;
}) {
  const t = labels[locale];
  if (message.role === 'user') return <article className={styles.user} aria-label={t.you}><p>{message.text}</p></article>;
  return <article className={styles.reply} aria-label={t.title}>
    <div className={styles.byline}><Sprout size={14}/>{message.mode ? t[message.mode] : t.title}</div>
    <p>{message.text}</p>
    {visible&&<ReadChatReply text={message.text} locale={locale}/>}
    {!!message.sources?.length && <div className={styles.sources}>
      <strong><BookOpen size={13}/>{t.sources}</strong>
      <ul>{message.sources.map((source, i) => <li key={i}>
        {source.url && /^https?:\/\//i.test(source.url)
          ? <a href={source.url} target="_blank" rel="noreferrer">{source.label}<ArrowUpRight size={12}/></a>
          : <span>{source.label}</span>}
        {source.detail && <small>{source.detail}</small>}
      </li>)}</ul>
    </div>}
    {!!message.actions?.length && <div className={styles.actions}>{message.actions.map((action, i) => {
      if (action.kind === 'note') return <button key={i} type="button" disabled={busy || action.done} onClick={() => onNote(message.id)}>
        {action.done ? <Check size={14}/> : <NotebookPen size={14}/>} {action.done ? t.saved : action.label}
      </button>;
      if (action.kind === 'handoff') return <Handoff key={i} action={action} t={t}/>;
      if (action.kind === 'call' && action.target === 'tel:16123') return <a key={i} href={action.target}><Phone size={14}/>{action.label}</a>;
      if (action.kind === 'navigate' && /^\/[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*\/?$/.test(action.target))
        return <a key={i} href={'/' + locale + action.target}><ArrowUpRight size={14}/>{action.label}</a>;
      return null;
    })}</div>}
  </article>;
}

type PanelProps = ChatProps & {storeKey: string; visible: boolean; onClose: () => void; context: OpenContext};
function HistoryView({locale, plotId, caseId, entries, choose, back}: Pick<ChatProps, 'locale' | 'plotId' | 'caseId'> &
  {entries: Index['entries']; choose: (id: string, date: number) => void; back: () => void}) {
  const t = labels[locale];
  const [recent, setRecent] = useState<Index['entries']>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const current = new AbortController();
    const query = new URLSearchParams();
    if (caseId) query.set('case_id', caseId);
    else if (plotId) query.set('plot_id', plotId);
    setState('loading');
    request<{items: {id: string; updated_at: string}[]}>('/farmer-chat/conversations?' + query, {signal: current.signal})
      .then(result => {
        if (current.signal.aborted) return;
        const rows = result.items.map(row => ({id: row.id, date: Date.parse(row.updated_at)}));
        setRecent(rows.filter(row => Number.isFinite(row.date)));
        setState('ready');
      })
      .catch(() => {if (!current.signal.aborted) setState('error');});
    return () => current.abort();
  }, [caseId, plotId, attempt]);
  const combined = new Map(entries.map(entry => [entry.id, entry]));
  for (const row of recent) combined.set(row.id, row);
  const ordered = Array.from(combined.values()).sort((a, b) => b.date - a.date);
  const n = new Intl.NumberFormat(locale === 'bn' ? 'bn-BD' : 'en-BD');
  const date = new Intl.DateTimeFormat(locale === 'bn' ? 'bn-BD' : 'en-BD', {timeZone: 'Asia/Dhaka', dateStyle: 'medium', timeStyle: 'short'});
  return <div className={styles.history}>
    <button type="button" className={styles.back} onClick={back}><ChevronLeft size={15}/>{t.back}</button>
    <h3>{t.history}</h3>
    {state === 'loading' && <p role="status">{t.listLoading}</p>}
    {state === 'error' && <div className={styles.failure}><p role="alert">{t.listFailed}</p><button type="button" onClick={() => setAttempt(n => n + 1)}>{t.retry}</button></div>}
    {ordered.map((entry, i) => <button className={styles.historyItem} type="button" key={entry.id} onClick={() => choose(entry.id, entry.date)}>
      <MessageCircle size={17}/><span>{t.previous} {n.format(ordered.length - i)}<small>{date.format(entry.date)}</small></span><ArrowRight size={15}/>
    </button>)}
    {!ordered.length && state === 'ready' && <p>{t.noHistory}</p>}
  </div>;
}

function ChatPanel({locale, plotId, plotName, caseId, storeKey, visible, onClose, context}: PanelProps) {
  const t = labels[locale];
  const queries = useQueryClient();
  const [index, setIndex] = useState(() => readIndex(storeKey));
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [history, setHistory] = useState(false);
  const [draft, setDraft] = useState(context.draft || '');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [pending, setPending] = useState<Operation | null>(null);
  const [failure, setFailure] = useState<{operation: Operation; error: unknown} | null>(null);
  const controller = useRef<AbortController | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const activeId = index.active;
  const loaded = conversation?.conversation_id === activeId;

  function remember(next: Index) {
    setIndex(next);
    try { localStorage.setItem(storeKey, JSON.stringify(next)); } catch { /* The in-memory index remains usable. */ }
  }

  useEffect(() => {
    if (!activeId || loaded) return;
    const operation: Operation = {kind: 'load', id: activeId};
    const current = new AbortController();
    controller.current = current;
    setPending(operation);
    setFailure(null);
    request<Conversation>('/farmer-chat/conversations/' + encodeURIComponent(activeId), {signal: current.signal})
      .then(result => {if (!current.signal.aborted) setConversation(result);})
      .catch(error => {if (!current.signal.aborted) setFailure({operation, error});})
      .finally(() => {
        if (controller.current === current) {
          controller.current = null;
          setPending(null);
        }
      });
    return () => {current.abort();};
  }, [activeId, loaded, loadAttempt]);

  useEffect(() => () => {controller.current?.abort(); controller.current = null;}, []);
  useEffect(() => {
    if (visible) heading.current?.focus({preventScroll: true});
  }, [visible]);
  useEffect(() => {
    if (context.draft !== undefined) {
      setDraft(context.draft);
      setHistory(false);
      input.current?.focus({preventScroll: true});
    }
  }, [context]);
  useEffect(() => {
    if (visible && list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [conversation, pending, failure, visible, history]);

  function choose(id: string | null, date?: number) {
    controller.current?.abort();
    controller.current = null;
    setConversation(null);
    const entries = id && date && !index.entries.some(entry => entry.id === id) ? [...index.entries, {id, date}] : index.entries;
    remember({entries, active: id});
    setDraft('');
    setFailure(null);
    setPending(null);
    setHistory(false);
    if (id && id === activeId && !loaded) setLoadAttempt(n => n + 1);
    requestAnimationFrame(() => (id ? heading.current : input.current)?.focus({preventScroll: true}));
  }

  async function perform(operation: Exclude<Operation, {kind: 'load'}>) {
    if (controller.current || (activeId && !loaded)) return;
    const current = new AbortController();
    controller.current = current;
    setPending(operation);
    setFailure(null);
    if (operation.kind === 'send') setDraft('');
    try {
      const isSend = operation.kind === 'send';
      const path = isSend ? '/farmer-chat/messages' : '/farmer-chat/conversations/' + encodeURIComponent(activeId!) + '/notes';
      const body = isSend ? {request_id: operation.id, message: operation.text, locale, plot_id: plotId, case_id: caseId,
        conversation_id: activeId || undefined} : {message_id: operation.id};
      const result = await request<Conversation>(path, {method: 'POST', body: JSON.stringify(body), signal: current.signal});
      if (current.signal.aborted) return;
      setConversation(result);
      if (operation.kind === 'note' && caseId) {
        void queries.invalidateQueries({queryKey: ['case', caseId]});
        void queries.invalidateQueries({queryKey: ['cases']});
      }
      const entries = index.entries.filter(entry => entry.id !== result.conversation_id);
      remember({active: result.conversation_id, entries: [{id: result.conversation_id, date: new Date().getTime()}, ...entries]});
    } catch (error) {
      if (current.signal.aborted) return;
      setFailure({operation, error});
      if (operation.kind === 'send') setDraft(operation.text);
    } finally {
      if (controller.current === current) {controller.current = null; setPending(null);}
    }
  }

  function send(text: string) {
    const question = text.trim();
    if (!question || Array.from(question).length > 1600) return;
    const last = failure?.operation;
    void perform(last?.kind === 'send' && last.text === question ? last : {kind: 'send', text: question, id: newRequestId()});
  }
  function retry() {
    const operation = failure?.operation;
    if (operation?.kind === 'load') setLoadAttempt(n => n + 1);
    if (operation?.kind === 'send') send(draft);
    if (operation?.kind === 'note') void perform(operation);
  }
  const prompts = caseId
    ? [{icon: ScanLine, label: t.explain}, {icon: Leaf, label: t.next}, {icon: FileText, label: t.adviser}]
    : [{icon: Leaf, label: t.plant}, {icon: CloudRain, label: t.rain}, {icon: ShoppingBasket, label: t.market}];
  const errorStatus = failure?.error instanceof ApiError ? failure.error.status : 0;
  const errorMessage = errorStatus === 401 ? t.expired : errorStatus === 429 ? t.rated : errorStatus === 413 ? t.tooLong : errorStatus === 409 ? t.conflict :
    failure?.operation.kind === 'load' ? t.loadFailed : failure?.operation.kind === 'note' ? t.noteFailed : t.failed;
  const busy = !!pending || (!!activeId && !loaded);
  const tooLong = Array.from(draft.trim()).length > 1600;
  return <section hidden={!visible} className={styles.panel} role="dialog" aria-labelledby="farmer-chat-title" id="farmer-chat-panel" lang={locale}
    onKeyDown={e => {if (e.key === 'Escape' && !e.nativeEvent.isComposing) {e.stopPropagation(); onClose();}}}>
    <header className={styles.header}>
      <ChatMark/>
      <div className={styles.identity}><h2 id="farmer-chat-title" tabIndex={-1} ref={heading}>{t.title}</h2>
        <span>{caseId ? <ScanLine size={12}/> : plotName ? <MapPin size={12}/> : null}
          {caseId ? t.screening : plotName || t.farm}</span>
      </div>
      <div className={styles.controls}>
        <button type="button" aria-label={t.history} title={t.history} disabled={pending?.kind === 'send' || pending?.kind === 'note'} aria-pressed={history} onClick={() => setHistory(!history)}><History size={18}/></button>
        <button type="button" aria-label={t.new} title={t.new} disabled={pending?.kind === 'send' || pending?.kind === 'note'} onClick={() => choose(null)}><SquarePen size={17}/></button>
        <button type="button" aria-label={t.close} title={t.close} onClick={onClose}><X size={19}/></button>
      </div>
    </header>
    {history ? <HistoryView locale={locale} caseId={caseId} plotId={plotId} entries={index.entries} choose={choose} back={() => setHistory(false)}/> : <>
      <div className={styles.stream} ref={list}>
        {!activeId && !conversation && !pending && !failure && <div className={styles.welcome}>
          <h3>{t.welcome}</h3>
          {prompts.map(({icon: Icon, label}) => <button type="button" key={label} onClick={() => {heading.current?.focus({preventScroll: true}); send(label);}}>
            <Icon size={17}/><span>{label}</span><ArrowRight size={15}/>
          </button>)}
        </div>}
        <div role="log" aria-label={t.title} aria-live="polite" aria-relevant="additions" className={styles.log}>
          {conversation?.messages.map(message => <Reply key={message.id} message={message} locale={locale} busy={busy} visible={visible}
            onNote={id => void perform({kind: 'note', id})}/>)}
          {pending?.kind === 'send' && <article className={styles.user} aria-label={t.you}><p>{pending.text}</p></article>}
        </div>
        {pending && <p role="status" className={styles.status}><LoaderCircle size={16} className={styles.spinner}/>{pending.kind === 'send' ? t.sending : pending.kind === 'load' ? t.loading : t.saving}</p>}
        {failure && <div className={styles.failure}><p role="alert">{errorMessage}</p>
          <button type="button" onClick={retry} disabled={failure.operation.kind === 'send' && (!draft.trim() || tooLong)}>{t.retry}</button>
        </div>}
      </div>
      {tooLong && <p className={styles.limit} id="farmer-chat-limit" role="status">{t.tooLong}</p>}
      {visible&&<ChatDictation locale={locale} disabled={busy} onTranscript={text => setDraft(previous => previous.trim() ? previous.trimEnd() + ' ' + text : text)}/>}
      <form className={styles.composer} onSubmit={e => {e.preventDefault(); send(draft);}}>
        <textarea ref={input} rows={2} value={draft} readOnly={!!pending} aria-label={t.input} aria-invalid={tooLong} aria-describedby={tooLong ? 'farmer-chat-limit' : undefined} placeholder={t.placeholder} onChange={e => setDraft(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.nativeEvent.keyCode !== 229) {
              e.preventDefault(); if (!busy) send(draft);
            }
          }}/>
        <button type="submit" aria-label={t.send} title={t.send} disabled={busy || !draft.trim() || tooLong}><ArrowUp size={20}/></button>
      </form>
    </>}
  </section>;
}

function Launcher(props: ChatProps) {
  const t = labels[props.locale];
  const [opened, setOpened] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [scope, setScope] = useState<{plotId?: string; event: OpenContext}>({plotId: props.plotId, event: {}});
  if (scope.plotId !== props.plotId) {
    // The workspace resolves its initial plot asynchronously. Keep a preview
    // opened during bootstrap, then clear it on an actual plot switch.
    setScope({plotId: props.plotId, event: scope.plotId ? {} : scope.event});
  }
  const context = scope.event;
  const launcher = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  function open() {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setMounted(true);
    setOpened(true);
  }
  function close() {
    setOpened(false);
    requestAnimationFrame(() => {
      const target = opener.current;
      (target?.isConnected && target !== document.body && !target.closest('#farmer-chat-panel') ? target : launcher.current)?.focus();
    });
  }
  useEffect(() => {
    const handle = (e: Event) => {
      const detail = (e as CustomEvent<OpenContext>).detail;
      setScope({plotId: props.plotId, event: {caseId: detail?.caseId, plotId: detail?.plotId, draft: detail?.draft}});
      open();
    };
    window.addEventListener('agrosphere:open-farmer-chat', handle);
    return () => window.removeEventListener('agrosphere:open-farmer-chat', handle);
  }, [props.plotId]);
  const caseId = context.caseId || props.caseId;
  const plotId = context.plotId || (context.caseId ? undefined : props.plotId);
  const storeKey = 'agrosphere-farmer-chat:' + JSON.stringify([props.userId, caseId ? 'case' : 'plot', caseId || plotId || null]);
  return <div className={styles.dock}>
    {mounted && <ChatPanel {...props} key={storeKey} caseId={caseId} plotId={plotId}
      plotName={plotId === props.plotId ? props.plotName : undefined} context={context} storeKey={storeKey} visible={opened} onClose={close}/>}
    <button type="button" ref={launcher} hidden={opened} className={styles.launcher} aria-label={t.title} aria-haspopup="dialog"
      aria-expanded={opened} aria-controls={mounted ? 'farmer-chat-panel' : undefined} onClick={open}><ChatMark/><span>{t.title}</span></button>
  </div>;
}

export function FarmerChat(props: ChatProps) {
  const path = usePathname();
  return <Launcher key={JSON.stringify([path, props.userId, props.caseId])} {...props}/>;
}
