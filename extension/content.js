// Content script for TuneLinkr
// This script rewrites music links on the page to point at the redirector backend.
// It listens for changes in the DOM to handle dynamically added links.
console.log("[TuneLinkr] content.js loaded");

let redirectorBase = 'http://localhost:8000'; // Default fallback

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

function buildRedirectUrl(originalHref, pref, deepLinks) {
  let redirectUrl = `${redirectorBase}/redirect?url=${encodeURIComponent(originalHref)}`;
  if (pref) {
    redirectUrl += `&pref=${encodeURIComponent(pref)}`;
  }
  if (deepLinks) {
    redirectUrl += `&deep_link=true`;
  }
  return redirectUrl;
}

function rewriteLinks(pref, deepLinks) {
  const anchors = document.querySelectorAll('a[href]');
  anchors.forEach(anchor => {
    if (!anchor.dataset.tunelinkrProcessed && isMusicLink(anchor.href)) {
      const originalHref = anchor.href;
      const newHref = buildRedirectUrl(originalHref, pref, deepLinks);
      anchor.setAttribute('href', newHref);
      // mark as processed
      anchor.dataset.tunelinkrProcessed = 'true';
    }
  });
}

function getBackendUrl(backendEnvironment, customBackendUrl) {
  switch (backendEnvironment) {
    case 'localhost':
      return 'http://localhost:8000';
    case 'railway':
      return 'https://web-production-27b4.up.railway.app'; 
    case 'custom':
      return customBackendUrl || 'http://localhost:8000';
    default:
      return 'http://localhost:8000';
  }
}

// Load user settings from chrome.storage and rewrite links accordingly
function init() {
  chrome.storage.sync.get(['enabled', 'pref', 'backendEnvironment', 'customBackendUrl', 'deepLinks'], (items) => {
    const enabled = items.enabled !== false; // default to enabled
    const pref = items.pref || null;
    const backendEnvironment = items.backendEnvironment || 'localhost';
    const customBackendUrl = items.customBackendUrl || '';
    const deepLinks = items.deepLinks === true;
    
    // Set the backend URL based on user selection
    redirectorBase = getBackendUrl(backendEnvironment, customBackendUrl);
    
    console.log(`[TuneLinkr] Using backend: ${redirectorBase}`);
    console.log(`[TuneLinkr] Deep links enabled: ${deepLinks}`);
    
    if (!enabled) return;
    // initial rewrite
    rewriteLinks(pref, deepLinks);
    // watch for future DOM changes
    const observer = new MutationObserver(() => rewriteLinks(pref, deepLinks));
    observer.observe(document.body || document.documentElement, { childList: true, subtree: true });
  });
}

// Wait until DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}