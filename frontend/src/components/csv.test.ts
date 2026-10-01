import { describe, it, expect } from 'vitest';
import { toCsv } from './csv';

describe('toCsv', () => {
  it('writes header and rows', () => {
    const out = toCsv(
      [{ a: 1, b: 'x' }, { a: 2, b: 'y' }],
      ['a', 'b'],
    );
    expect(out).toBe('a,b\n1,x\n2,y');
  });

  it('quotes values containing commas', () => {
    const out = toCsv([{ a: 'x,y' }], ['a']);
    expect(out).toBe('a\n"x,y"');
  });

  it('escapes double-quotes by doubling them', () => {
    const out = toCsv([{ a: 'he said "hi"' }], ['a']);
    expect(out).toBe('a\n"he said ""hi"""');
  });

  it('renders null/undefined as empty cell', () => {
    const out = toCsv([{ a: null, b: undefined, c: 0 }], ['a', 'b', 'c']);
    expect(out).toBe('a,b,c\n,,0');
  });

  it('preserves column order from cols arg', () => {
    const out = toCsv([{ b: 2, a: 1 }], ['a', 'b']);
    expect(out).toBe('a,b\n1,2');
  });
});
