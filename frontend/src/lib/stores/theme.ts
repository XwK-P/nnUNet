export type Theme = 'light' | 'dark' | 'system';

const KEY = 'nnunet-gui:theme';

function apply(theme: Theme): void {
  const html = document.documentElement;
  const dark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  html.classList.toggle('dark', dark);
}

export function createThemeStore() {
  let current: Theme = (localStorage.getItem(KEY) as Theme | null) ?? 'system';
  apply(current);

  return {
    get(): Theme {
      return current;
    },
    set(next: Theme): void {
      current = next;
      localStorage.setItem(KEY, next);
      apply(next);
    },
  };
}
