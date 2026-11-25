export const NOTEBOOK_KEY = 'agrosphere-encrypted-notebook-v1';

export type Notebook = {
  locale: 'en' | 'bn';
  title: string;
  groups: {title: string; items: string[]}[];
};

function base64(bytes: Uint8Array) {
  // Use bounded chunks so larger notebooks stay within call-stack limits.
  let raw = '';
  for (let i = 0; i < bytes.length; i += 8192) raw += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(raw);
}

export async function saveNotebook(notebook: Notebook, passphrase: string, stillSignedIn: () => boolean) {
  if (!window.isSecureContext || !('serviceWorker' in navigator) || !crypto.subtle) {
    throw new Error('The offline notebook needs HTTPS or localhost.');
  }
  const registration = await navigator.serviceWorker.register('/farm-notebook-worker.js');
  if (!registration.active) {
    const worker = registration.installing || registration.waiting;
    if (!worker) throw new Error('The offline notebook could not install.');
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => finish(new Error('The offline notebook download timed out.')), 15000);
      function finish(error?: Error) {
        window.clearTimeout(timeout);
        worker?.removeEventListener('statechange', check);
        if (error) reject(error);
        else resolve();
      }
      function check() {
        if (worker?.state === 'activated') finish();
        if (worker?.state === 'redundant') finish(new Error('The offline notebook could not download its files.'));
      }
      worker.addEventListener('statechange', check);
      check();
    });
  }
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const secret = await crypto.subtle.importKey('raw', new TextEncoder().encode(passphrase), 'PBKDF2', false, ['deriveKey']);
  const cipher = await crypto.subtle.deriveKey({
    name:'PBKDF2', salt, iterations:600000, hash:'SHA-256',
  }, secret, {name:'AES-GCM', length:256}, false, ['encrypt']);
  const encoded = new TextEncoder().encode(JSON.stringify({...notebook, savedAt: new Date().toISOString()}));
  const data = await crypto.subtle.encrypt({name:'AES-GCM', iv}, cipher, encoded);
  if (!stillSignedIn()) throw new Error('Sign in again before saving the notebook.');
  window.localStorage.setItem(NOTEBOOK_KEY, JSON.stringify({
    version:1, salt:base64(salt), iv:base64(iv), data:base64(new Uint8Array(data)),
  }));
}
