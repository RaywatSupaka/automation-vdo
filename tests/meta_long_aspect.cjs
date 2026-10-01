const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert/strict');

const source = fs.readFileSync(path.join(__dirname,
  '../browser_extension/src/platforms/meta-ai/video.js'), 'utf8');
const sandbox = {URL, Date, console};
vm.runInNewContext(source.replaceAll('export ', '') +
  '\nthis.metaChoiceOffer=metaChoiceOffer;this.metaSafeOffer=metaSafeOffer;this.metaFollowupOffer=metaFollowupOffer;', sandbox);
const options = 'Option 1: A static image. Option 2: A train moving gently through the valley. Want me to generate that video?';
const safer = 'I could not generate the video from this starting frame. I can make a safer version with a wider framing. Want me to try?';
const choiceShort = sandbox.metaChoiceOffer(options);
const choiceLong = sandbox.metaChoiceOffer(options, '16:9');
const safeShort = sandbox.metaSafeOffer(safer);
const safeLong = sandbox.metaSafeOffer(safer, '16:9');
assert(choiceShort && choiceLong && safeShort && safeLong);
assert.match(choiceShort.prompt, /vertical 9:16/);
assert.match(choiceLong.prompt, /landscape 16:9/);
assert.match(safeShort.prompt, /vertical 9:16/);
assert.match(safeLong.prompt, /landscape 16:9/);
assert.equal(sandbox.metaFollowupOffer(options, '16:9').prompt, choiceLong.prompt);
assert.equal(sandbox.metaFollowupOffer(safer, '16:9').prompt, safeLong.prompt);
console.log(JSON.stringify({options, safer, choiceShort, choiceLong, safeShort, safeLong}));
