// Options page script for TuneLinkr

document.addEventListener('DOMContentLoaded', () => {
  const enabledCheckbox = document.getElementById('enabled');
  const status = document.getElementById('status');
  const saveBtn = document.getElementById('save');

  // Load existing settings
  chrome.storage.sync.get(['enabled', 'pref'], (items) => {
    enabledCheckbox.checked = items.enabled !== false;
    const pref = items.pref || null;
    if (pref) {
      const radio = document.querySelector(`input[name="pref"][value="${pref}"]`);
      if (radio) radio.checked = true;
    }
  });

  saveBtn.addEventListener('click', () => {
    const enabled = enabledCheckbox.checked;
    const prefRadio = document.querySelector('input[name="pref"]:checked');
    const pref = prefRadio ? prefRadio.value : null;
    chrome.storage.sync.set({ enabled, pref }, () => {
      status.textContent = 'Settings saved.';
      setTimeout(() => status.textContent = '', 2000);
    });
  });
});