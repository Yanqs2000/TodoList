import { describe, expect, it } from 'vitest';
import { encodeWav } from '../wav';

function ascii(view: DataView, offset: number, length: number): string {
  let text = '';
  for (let i = 0; i < length; i += 1) text += String.fromCharCode(view.getUint8(offset + i));
  return text;
}

describe('encodeWav', () => {
  it('writes a valid RIFF/WAVE header', () => {
    const buffer = encodeWav(new Float32Array([0, 0.5, -0.5]), 16000);
    const view = new DataView(buffer);

    expect(ascii(view, 0, 4)).toBe('RIFF');
    expect(view.getUint32(4, true)).toBe(36 + 6);
    expect(ascii(view, 8, 4)).toBe('WAVE');
    expect(ascii(view, 12, 4)).toBe('fmt ');
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint16(34, true)).toBe(16); // bits
    expect(ascii(view, 36, 4)).toBe('data');
    expect(view.getUint32(40, true)).toBe(6);
    expect(buffer.byteLength).toBe(44 + 6);
  });

  it('converts float samples to int16 with clamping', () => {
    const buffer = encodeWav(new Float32Array([0, 1, -1, 2]), 16000);
    const view = new DataView(buffer);

    expect(view.getInt16(44, true)).toBe(0);
    expect(view.getInt16(46, true)).toBe(0x7fff);
    expect(view.getInt16(48, true)).toBe(-0x8000);
    expect(view.getInt16(50, true)).toBe(0x7fff); // 2 clamped to 1
  });
});
