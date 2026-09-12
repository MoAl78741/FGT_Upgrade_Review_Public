import outfit from '@fontsource/outfit/files/outfit-latin-400-normal.woff2?inline';
import outfitBold from '@fontsource/outfit/files/outfit-latin-600-normal.woff2?inline';
import mono from '@fontsource/jetbrains-mono/files/jetbrains-mono-latin-400-normal.woff2?inline';
/** Data URLs keep downloaded HTML/PDF typography independent of any network. */
export const exportFontCss = `
@font-face { font-family: Outfit; font-style: normal; font-weight: 400; src: url(${outfit}) format('woff2'); }
@font-face { font-family: Outfit; font-style: normal; font-weight: 600; src: url(${outfitBold}) format('woff2'); }
@font-face { font-family: 'JetBrains Mono'; font-style: normal; font-weight: 400; src: url(${mono}) format('woff2'); }
`;
