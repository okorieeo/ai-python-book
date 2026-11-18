import { Colors } from '@/constants/colors';

import { contrastRatio } from '../../test/contrast';

// [text colour, background colour, minimum contrast]
const pairs: [keyof typeof Colors.light, keyof typeof Colors.light, number][] = [
  ['text', 'background', 4.5],
  ['text', 'backgroundElement', 4.5],
  ['text', 'backgroundSelected', 4.5],
  ['textSecondary', 'background', 4.5],
  ['textSecondary', 'backgroundElement', 4.5],
  ['onPrimary', 'primary', 4.5], // text on a primary button or bubble
  ['danger', 'background', 4.5], // error messages
  ['primary', 'background', 4.5], // links
  ['inputBorder', 'background', 3], // the outline of a text box
];

describe.each(['light', 'dark'] as const)('%s colour tokens', (scheme) => {
  it.each(pairs)('%s on %s has contrast of at least %s:1', (fg, bg, min) => {
    expect(contrastRatio(Colors[scheme][fg], Colors[scheme][bg])).toBeGreaterThanOrEqual(min);
  });
});
