chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.type !== 'roundtrip') return;
  (async () => {
    await chrome.storage.local.set({candidate: message.candidate});
    const {candidate} = await chrome.storage.local.get('candidate');
    respond({stored: candidate, transported: message.candidate});
  })();
  return true;
});
