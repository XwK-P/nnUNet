import { describe, it, expect, beforeEach } from 'vitest';
import { createThemeStore, type Theme } from './theme';

describe('theme store', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('dark');
  });

  it('defaults to "system"', () => {
    const t = createThemeStore();
    expect(t.get()).toBe<Theme>('system');
  });

  it('applies the "dark" class when set to dark', () => {
    const t = createThemeStore();
    t.set('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('removes the "dark" class when set to light', () => {
    document.documentElement.classList.add('dark');
    const t = createThemeStore();
    t.set('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('persists the choice to localStorage', () => {
    const t = createThemeStore();
    t.set('dark');
    expect(localStorage.getItem('nnunet-gui:theme')).toBe('dark');
  });

  it('restores from localStorage on construction', () => {
    localStorage.setItem('nnunet-gui:theme', 'dark');
    const t = createThemeStore();
    expect(t.get()).toBe<Theme>('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });
});
