'use client';

import {useEffect, useRef, useState} from 'react';
import {Mic, Square, Volume2} from 'lucide-react';

type Locale = 'en' | 'bn';
type Recognition = {
  lang: string;
  onresult: ((event: {results: ArrayLike<ArrayLike<{transcript:string}>>}) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: {error:string}) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};
type SpeechBrowser = Window & {
  SpeechRecognition?: new () => Recognition;
  webkitSpeechRecognition?: new () => Recognition;
};

export function ChatDictation({locale, disabled, onTranscript}: {
  locale: Locale;
  disabled: boolean;
  onTranscript: (text: string) => void;
}) {
  const bn = locale === 'bn';
  const active = useRef<Recognition | null>(null);
  const [listening, setListening] = useState(false);
  const [notice, setNotice] = useState('');
  useEffect(() => () => {
    const recognition = active.current;
    if (!recognition) return;
    recognition.onend = recognition.onerror = recognition.onresult = null;
    recognition.abort();
    active.current = null;
  }, []);

  function toggle() {
    if (active.current) {
      active.current.stop();
      return;
    }
    const browser = window as SpeechBrowser;
    const Recognizer = browser.SpeechRecognition || browser.webkitSpeechRecognition;
    if (!Recognizer || !window.isSecureContext) {
      setNotice(bn ? 'এই ব্রাউজারে ভয়েস ইনপুট পাওয়া যায়নি। লিখে প্রশ্ন করুন।' : 'Dictation is unavailable here. You can type your question.');
      return;
    }
    const recognition = new Recognizer();
    active.current = recognition;
    recognition.lang = bn ? 'bn-BD' : 'en-BD';
    recognition.onresult = event => {
      const text = event.results[0]?.[0]?.transcript.trim();
      if (text) {
        onTranscript(text);
        setNotice(bn ? 'পাঠানোর আগে লেখা দেখুন।' : 'Review the transcript before sending.');
      }
    };
    recognition.onerror = event => {
      if (event.error === 'aborted') return;
      setNotice(event.error === 'not-allowed'
        ? (bn ? 'মাইক্রোফোনের অনুমতি দিন বা লিখে প্রশ্ন করুন।' : 'Allow microphone access or type your question.')
        : (bn ? 'কথা বোঝা যায়নি। আবার বলুন বা লিখুন।' : 'Speech was unavailable. Try again or type your question.'));
    };
    recognition.onend = () => {active.current = null; setListening(false);};
    try {
      setListening(true);
      setNotice(bn ? 'শুনছি…' : 'Listening…');
      recognition.start();
    } catch {
      active.current = null;
      setListening(false);
      setNotice(bn ? 'মাইক্রোফোন চালু হয়নি।' : 'The microphone could not start.');
    }
  }

  return <span className="chat-dictation">
    <button type="button" className="text-link" onClick={toggle} disabled={disabled && !listening} aria-pressed={listening}>
      {listening ? <Square size={15}/> : <Mic size={15}/>}
      {listening ? (bn ? 'শোনা বন্ধ করুন' : 'Stop listening') : (bn ? 'বলে প্রশ্ন করুন' : 'Speak your question')}
    </button>
    <small>{bn ? 'ব্রাউজারের ভয়েস সেবা অডিও প্রক্রিয়া করতে পারে।' : 'Your browser’s speech service may process audio.'}</small>
    {notice && <small role="status">{notice}</small>}
  </span>;
}

export function ReadChatReply({locale, text}: {locale: Locale; text: string}) {
  const bn = locale === 'bn';
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => () => {
    if (utterance.current) window.speechSynthesis.cancel();
  }, []);

  function toggle() {
    if (!('speechSynthesis' in window)) {
      setError(true);
      return;
    }
    const system = window.speechSynthesis;
    if (utterance.current) {
      system.cancel();
      utterance.current = null;
      setPlaying(false);
      return;
    }
    const voice = system.getVoices().find(item => item.lang.slice(0,2).toLowerCase() === locale);
    if (!voice) {
      setError(true);
      return;
    }
    system.cancel();
    const item = new SpeechSynthesisUtterance(text);
    item.voice = voice;
    item.lang = voice.lang;
    utterance.current = item;
    setError(false);
    setPlaying(true);
    item.onend = item.onerror = () => {
      if (utterance.current !== item) return;
      utterance.current = null;
      setPlaying(false);
    };
    system.speak(item);
  }
  return <div className="chat-dictation">
    <button type="button" className="text-link" onClick={toggle} aria-pressed={playing}>
      {playing ? <Square size={14}/> : <Volume2 size={14}/>}
      {playing ? (bn ? 'পড়া বন্ধ করুন' : 'Stop reading') : (bn ? 'উত্তর শুনুন' : 'Read reply aloud')}
    </button>
    {error && <small role="status">{bn ? 'এই ডিভাইসে বাংলা কণ্ঠ পাওয়া যায়নি।' : 'No English voice is available on this device.'}</small>}
  </div>;
}
