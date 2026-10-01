// Transport-only instruction; canonical task/receipt identity stays compatible.
(() => {
  const instruction = '[SmartFlow response format v1] Return exactly one final answer for this request. Do not offer alternative responses, numbered choices, or ask me to choose. Choose one suitable solution yourself. Keep the requested schema, all required scenes/items, facts, dialogue and audio settings unchanged. If JSON is requested, return one complete JSON value only. If an image or video is requested, create exactly one actual media result, not a description of a result. Report genuine failure or unavailability truthfully.';
  const normal = value => String(value || '').replace(/\s+/g, ' ').trim();
  const has = value => normal(value).endsWith(instruction);
  const canonical = value => has(value) ? normal(value).slice(0, -instruction.length).trimEnd() : String(value || '');
  const wrap = value => !normal(value) || has(value) ? String(value || '') : String(value).trimEnd() + '\n\n' + instruction;
  globalThis.SmartFlowSingleAnswer = Object.freeze({instruction, has, canonical, wrap});
})();

// Versioned desktop-authored audio policy for a confirmed Flow rewrite only.
// Legacy transport and accepted/in-flight receipt bytes remain unchanged.
(() => {
  const start = 'AI GENERATED MUSIC v1:', end = '[END AI GENERATED MUSIC]';
  const moods = ['matching the mood of this scene', 'with a warm, gentle mood', 'with a light, cheerful mood',
    'with gentle, restrained suspense', 'with a tender, emotional mood'];
  const directives = new Set(moods.flatMap(mood => [false, true].map(api =>
    `${start} Add subtle original instrumental background music ${mood}. Keep dialogue clearly dominant. No singing or lyrics. Use gentle entry and exit.`
    + (api ? ' No generated speech; narration is added separately.' : '') + ` ${end}`)));
  function extract(value) {
    const matches = String(value || '').match(/AI GENERATED MUSIC v1:[\s\S]*?\[END AI GENERATED MUSIC\]/g) || [];
    const owned = matches.filter(item => directives.has(item));
    return owned.length === 1 ? owned[0] : '';
  }
  function finalizeCandidate(record, candidate) {
    if (record?.scope !== 'flow' || !record.generated_music_instruction) return candidate;
    if (!directives.has(record.generated_music_instruction)) throw Error('Invalid frozen generated music instruction');
    if (!candidate || candidate.needs_review !== false || candidate.reference_compatible !== true
        || candidate.material_change !== false || typeof candidate.prompt !== 'string') return candidate;
    const replacements = [
      ['Include natural ambient sounds only.', 'Include natural ambient sounds.'],
      ['No music, speech or ambient audio; narration is added separately.', 'No generated speech; narration is added separately.'],
      ['No speech or music; narration is added separately.', 'No generated speech; narration is added separately.'],
      ['Do not add music, captions or subtitles.', 'Do not add captions or subtitles.'],
      ['No extra dialogue, background music or burned-in captions.', 'No extra dialogue or burned-in captions.'],
      ['Do not invent spoken lines or music.', 'Do not invent spoken lines.']
    ];
    let prompt = candidate.prompt.replace(/\n?AI GENERATED MUSIC v1:[\s\S]*?\[END AI GENERATED MUSIC\]/g, '');
    const parts = prompt.split(/("(?:\\.|[^"\\])*"|(?<!\w)'(?:\\.|[^'\\])*'(?!\w)|Spoken line: [^\n]*|^[ \t]*(?:Scene:|Story action:|Action:|Dialogue:) [^\n]*)/gim);
    for (let index = 0; index < parts.length; index += 2) {
      for (const [before, after] of replacements) {
        const escaped = before.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        parts[index] = parts[index].replace(new RegExp(escaped, 'gi'), after);
      }
      parts[index] = parts[index].replace(/(?<!\w)(?:No background music|No music|Do not add background music|Do not add music|Without background music|Without music)\b[ \t]*(?:[.;]|(?=$|\n))/gi, '');
    }
    prompt = parts.join('') + '\n' + record.generated_music_instruction;
    return {...candidate, prompt};
  }
  function assertCandidate(record) {
    const checked = finalizeCandidate(record, record?.candidate);
    if (checked?.prompt !== record?.candidate?.prompt) throw Error('Flow music policy was not saved before preparation');
    return true;
  }
  globalThis.SmartFlowGeneratedMusic = Object.freeze({extract, finalizeCandidate, assertCandidate});
})();
