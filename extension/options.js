// Options page script for TuneLinkr

document.addEventListener('DOMContentLoaded', () => {
  const enabledCheckbox = document.getElementById('enabled');
  const status = document.getElementById('status');
  const saveBtn = document.getElementById('save');
  const customBackendDiv = document.getElementById('customBackendUrl');
  const backendBaseInput = document.getElementById('backendBase');

  // Show/hide custom URL input based on backend selection
  function toggleCustomBackend() {
    const customRadio = document.querySelector('input[name="backend"][value="custom"]');
    customBackendDiv.style.display = customRadio && customRadio.checked ? 'block' : 'none';
  }

  // Add event listeners to backend radio buttons
  document.querySelectorAll('input[name="backend"]').forEach(radio => {
    radio.addEventListener('change', toggleCustomBackend);
  });

  // Load existing settings
  chrome.storage.sync.get(['enabled', 'pref', 'backendEnvironment', 'customBackendUrl'], (items) => {
    enabledCheckbox.checked = items.enabled !== false;
    
    // Load music service preference
    const pref = items.pref || null;
    if (pref) {
      const radio = document.querySelector(`input[name="pref"][value="${pref}"]`);
      if (radio) radio.checked = true;
    }

    // Load backend environment preference
    const backendEnv = items.backendEnvironment || 'localhost';
    const backendRadio = document.querySelector(`input[name="backend"][value="${backendEnv}"]`);
    if (backendRadio) {
      backendRadio.checked = true;
    } else {
      // Default to localhost if no valid option found
      const localhostRadio = document.querySelector('input[name="backend"][value="localhost"]');
      if (localhostRadio) localhostRadio.checked = true;
    }

    // Load custom backend URL
    if (items.customBackendUrl) {
      backendBaseInput.value = items.customBackendUrl;
    }

    toggleCustomBackend();
  });

  saveBtn.addEventListener('click', () => {
    const enabled = enabledCheckbox.checked;
    const prefRadio = document.querySelector('input[name="pref"]:checked');
    const pref = prefRadio ? prefRadio.value : null;
    
    const backendRadio = document.querySelector('input[name="backend"]:checked');
    const backendEnvironment = backendRadio ? backendRadio.value : 'localhost';
    
    const customBackendUrl = backendBaseInput.value.trim();

    chrome.storage.sync.set({ 
      enabled, 
      pref, 
      backendEnvironment, 
      customBackendUrl 
    }, () => {
      status.textContent = 'Settings saved.';
      setTimeout(() => status.textContent = '', 2000);
    });
  });
});