// Popup script for TuneLinkr

document.addEventListener('DOMContentLoaded', () => {
  const enabledCheckbox = document.getElementById('enabled');
  const status = document.getElementById('status');
  const openOptions = document.getElementById('openOptions');

  chrome.storage.sync.get(['enabled'], (items) => {
    enabledCheckbox.checked = items.enabled !== false;
    status.textContent = 'TuneLinkr is ' + (enabledCheckbox.checked ? 'enabled' : 'disabled');
  });

  enabledCheckbox.addEventListener('change', () => {
    const enabled = enabledCheckbox.checked;
    chrome.storage.sync.set({ enabled }, () => {
      status.textContent = 'TuneLinkr is ' + (enabled ? 'enabled' : 'disabled');
    });
  });

  openOptions.addEventListener('click', (e) => {
    e.preventDefault();
    if (chrome.runtime.openOptionsPage) {
      chrome.runtime.openOptionsPage();
    } else {
      window.open('options.html');
    }
  });
});