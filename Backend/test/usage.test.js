import assert from 'node:assert/strict';
import { test } from 'node:test';

import { costOf, normaliseUsage, primaryModel } from '../src/modules/usage.js';

const fromAi = {
  prompt_tokens: 2710, completion_tokens: 418, total_tokens: 3128, calls: 3, estimated: false,
  by_model: [
    { model: 'meta/llama-3.3-70b-instruct', purpose: 'chat', calls: 2, prompt_tokens: 2698, completion_tokens: 418, estimated: false },
    { model: 'nvidia/nv-embedqa-e5-v5', purpose: 'embedding', calls: 1, prompt_tokens: 12, completion_tokens: 0, estimated: false },
  ],
};

test('usage is recomputed from the per-model rows, not trusted from the totals', () => {
  const u = normaliseUsage({ ...fromAi, total_tokens: 999999 });
  assert.equal(u.total_tokens, 3128);
  assert.equal(u.calls, 3);
  assert.equal(u.estimated, false);
});

test('malformed usage becomes zero, never an exception', () => {
  for (const bad of [undefined, null, 'x', { by_model: 'no' }, { by_model: [null, { model: '' }, { tokens: 5 }] }]) {
    assert.deepEqual(normaliseUsage(bad), {
      prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, calls: 0, estimated: false,
      audio_seconds: 0, characters: 0, by_model: [],
    });
  }
  const odd = normaliseUsage({ by_model: [{ model: 'm', purpose: 'hack', prompt_tokens: -5, completion_tokens: '7.9', calls: 'x' }] });
  assert.deepEqual(odd.by_model[0], {
    model: 'm', purpose: 'chat', calls: 0, prompt_tokens: 0, completion_tokens: 7, estimated: false,
    audio_seconds: 0, characters: 0,
  });
});

test('a flood of models is capped', () => {
  const many = { by_model: Array.from({ length: 50 }, (_, i) => ({ model: `m${i}`, prompt_tokens: 1 })) };
  assert.equal(normaliseUsage(many).by_model.length, 20);
});

test('cost per 1M tokens, input and output priced separately', () => {
  const prices = { a: { input: 0.5, output: 1.5 } };
  assert.equal(costOf('a', { prompt_tokens: 1_000_000, completion_tokens: 0 }, prices), 0.5);
  assert.equal(costOf('a', { prompt_tokens: 2000, completion_tokens: 1000 }, prices), 0.0025);
  assert.equal(costOf('unpriced', { prompt_tokens: 10 }, prices), null);
});

test('speech is priced per audio minute and per character', () => {
  const prices = { stt: { per_minute: 0.006 }, tts: { per_1m_characters: 15 } };
  assert.equal(costOf('stt', { audio_seconds: 30 }, prices), 0.003);
  assert.equal(costOf('tts', { characters: 2000 }, prices), 0.03);
});

test('speech usage survives normalisation; unknown purposes do not', () => {
  const u = normaliseUsage({ by_model: [
    { model: 'gpt-4o-transcribe', purpose: 'transcription', calls: 1, audio_seconds: 4.567, prompt_tokens: 60 },
    { model: 'gpt-4o-mini-tts', purpose: 'speech', calls: 2, characters: 180 },
    { model: 'x', purpose: 'mining', audio_seconds: -3 },
  ] });
  assert.deepEqual([u.audio_seconds, u.characters], [4.57, 180]);
  assert.deepEqual(u.by_model.map((m) => m.purpose), ['transcription', 'speech', 'chat']);
  assert.equal(u.by_model[2].audio_seconds, 0);
});

test('the answering model is the chat model that wrote the most', () => {
  assert.equal(primaryModel(normaliseUsage(fromAi)), 'meta/llama-3.3-70b-instruct');
  assert.equal(primaryModel(normaliseUsage({ by_model: [{ model: 'e', purpose: 'embedding' }] })), null);
});
