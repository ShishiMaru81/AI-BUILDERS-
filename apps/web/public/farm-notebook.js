'use strict';

const key = 'agrosphere-encrypted-notebook-v1';
const status = document.getElementById('status');
const snapshot = document.getElementById('snapshot');
const password = document.getElementById('password');
const form = document.getElementById('unlock');
const forget = document.getElementById('forget');

function fromBase64(value) {
  return Uint8Array.from(atob(value), character => character.charCodeAt(0));
}

function paragraph(container, tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  container.append(node);
  return node;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  snapshot.replaceChildren();
  status.textContent = '';
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      status.textContent = 'Save a notebook from Farm tools while online. / অনলাইনে খামারের কাজ থেকে খাতা সংরক্ষণ করুন।';
      return;
    }
    const envelope = JSON.parse(raw);
    if (envelope.version !== 1) throw new Error('Unsupported snapshot');
    const secret = await crypto.subtle.importKey('raw', new TextEncoder().encode(password.value), 'PBKDF2', false, ['deriveKey']);
    const cipher = await crypto.subtle.deriveKey({
      name:'PBKDF2', salt:fromBase64(envelope.salt), iterations:600000, hash:'SHA-256'
    }, secret, {name:'AES-GCM', length:256}, false, ['decrypt']);
    const bytes = await crypto.subtle.decrypt({name:'AES-GCM', iv:fromBase64(envelope.iv)}, cipher, fromBase64(envelope.data));
    const data = JSON.parse(new TextDecoder().decode(bytes));
    if (raw !== localStorage.getItem(key)) return;
    snapshot.lang = data.locale;
    const time = new Intl.DateTimeFormat(data.locale === 'bn' ? 'bn-BD' : 'en-BD', {
      dateStyle:'medium', timeStyle:'short', timeZone:'Asia/Dhaka'
    }).format(new Date(data.savedAt));
    paragraph(snapshot, 'h2', data.title);
    paragraph(snapshot, 'p', (data.locale === 'bn' ? 'সংরক্ষণ করা হয়েছে ' : 'Saved ') + time);
    for (const group of data.groups) {
      paragraph(snapshot, 'h3', group.title);
      const list = paragraph(snapshot, 'ul', '');
      for (const item of group.items) paragraph(list, 'li', item);
    }
  } catch {
    status.textContent = 'Could not unlock this copy. Check your passphrase. / খাতা খোলা যায়নি। পাসওয়ার্ড দেখুন।';
  } finally {
    password.value = '';
  }
});

function lock() {
  snapshot.replaceChildren();
  password.value = '';
}
window.addEventListener('pagehide', lock);
window.addEventListener('storage', event => { if (event.key === key) lock(); });
forget.addEventListener('click', () => {
  if (!window.confirm('Delete the offline copy on this device? / এই ডিভাইসের অফলাইন কপি মুছবেন?')) return;
  localStorage.removeItem(key);
  lock();
  status.textContent = 'Offline copy deleted. / অফলাইন কপি মুছে ফেলা হয়েছে।';
});
