// Content script for TuneLinkr
// This script rewrites music links on the page to point at the redirector backend.
// It listens for changes in the DOM to handle dynamically added links.
console.log("[TuneLinkr] content.js loaded");

let redirectorBase = 'http://localhost:8000';

// Domains considered music platforms
const MUSIC_DOMAINS = [
  'open.spotify.com',
  'spotify.com',
  'music.apple.com',
  'itunes.apple.com',
  'music.youtube.com',
  'youtube.com',
  'youtu.be'
];

function isMusicLink(href) {
  try {
    const url = new URL(href);
    return MUSIC_DOMAINS.some(domain => url.hostname.includes(domain));
  } catch (err) {
    return false;
  }
}

function buildRedirectUrl(originalHref, pref) {
  let redirectUrl = `${redirectorBase}/redirect?url=${encodeURIComponent(originalHref)}`;
  if (pref) {
    redirectUrl += `&pref=${encodeURIComponent(pref)}`;
  }
  return redirectUrl;
}

function rewriteLinks(pref) {
  const anchors = document.querySelectorAll('a[href]');
  anchors.forEach(anchor => {
    if (!anchor.dataset.tunelinkrProcessed && isMusicLink(anchor.href)) {
      const originalHref = anchor.href;
      const newHref = buildRedirectUrl(originalHref, pref);
      anchor.setAttribute('href', newHref);
      // mark as processed
      anchor.dataset.tunelinkrProcessed = 'true';
    }
  });
}

// Load user settings from chrome.storage and rewrite links accordingly
function init() {
  chrome.storage.sync.get(['enabled', 'pref', 'backendBase'], (items) => {
    const enabled = items.enabled !== false; // default to enabled
    const pref = items.pref || null;
    if (items.backendBase && typeof items.backendBase === 'string') {
      redirectorBase = items.backendBase;
    }
    if (!enabled) return;
    // initial rewrite
    rewriteLinks(pref);
    // watch for future DOM changes
    const observer = new MutationObserver(() => rewriteLinks(pref));
    observer.observe(document.body || document.documentElement, { childList: true, subtree: true });
  });
}

// Wait until DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}