/**
 * Colour tokens, named by purpose (the same idea as Chapter 19's web tokens).
 * Components ask for "primary" or "textSecondary", never for a hex value.
 */
export const Colors = {
  light: {
    text: '#0f172a',
    textSecondary: '#475569',
    background: '#ffffff',
    backgroundElement: '#f1f5f9',
    backgroundSelected: '#e2e8f0',
    primary: '#1d4ed8',
    onPrimary: '#ffffff',
    danger: '#b91c1c',
    border: '#e2e8f0',
    inputBorder: '#64748b',
  },
  dark: {
    text: '#e2e8f0',
    textSecondary: '#a3b1c6',
    background: '#0b1120',
    backgroundElement: '#1e293b',
    backgroundSelected: '#273449',
    primary: '#60a5fa',
    onPrimary: '#0b1120',
    danger: '#f87171',
    border: '#1e293b',
    inputBorder: '#64748b',
  },
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;
