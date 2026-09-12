/** Deliberately retains feature states only; never returns source values or identifiers. */
export const RULE_VERSION = '1';
export const FEATURES = ['SD-WAN', 'IPsec VPN', 'SSL VPN', 'BGP', 'OSPF', 'HA', 'VDOMs', 'Security profiles'] as const;
export type FeatureName = typeof FEATURES[number];
export type FeatureState = 'configured' | 'disabled' | 'unknown';
export type FeatureProfile = Record<FeatureName, FeatureState>;
export const emptyProfile = (): FeatureProfile => Object.fromEntries(FEATURES.map(f => [f, 'unknown'])) as FeatureProfile;
interface Block { name: string; kind: 'config' | 'edit'; settings: Map<string, string[]>; children: Block[] }
const paths: Record<FeatureName, RegExp> = {
  'SD-WAN': /^system (sdwan|virtual-wan-link)$/,
  'IPsec VPN': /^vpn ipsec phase1(-interface)?$/,
  'SSL VPN': /^vpn ssl settings$/,
  'BGP': /^router bgp$/, 'OSPF': /^router ospf6?$/, 'HA': /^system ha$/,
  'VDOMs': /^vdom$/, 'Security profiles': /^(antivirus|webfilter|dnsfilter|ips|application) (profile|sensor|list)$/,
};

function tokens(line: string): string[] {
  const result: string[] = [];
  let token = '', quote = false, escape = false, started = false;
  for (const c of line) {
    if (escape) { token += c; escape = false; started = true; }
    else if (c === '\\' && quote) escape = true;
    else if (c === '"') { quote = !quote; started = true; }
    else if (/\s/.test(c) && !quote) { if (started) result.push(token); token = ''; started = false; }
    else { token += c; started = true; }
  }
  if (quote || escape) throw new Error('Unsupported multiline or unterminated quoted value. Use a plaintext FortiOS backup.');
  if (started) result.push(token);
  return result;
}

function logicalLines(text: string): string[] {
  const lines: string[] = [];
  let pending = '', quote = false, escape = false;
  for (const raw of text.split(/\r?\n/)) {
    if (!pending && (!raw.trim() || raw.trim().startsWith('#'))) continue;
    pending += (pending ? '\n' : '') + raw;
    for (const c of raw) {
      if (escape) escape = false;
      else if (c === '\\' && quote) escape = true;
      else if (c === '"') quote = !quote;
    }
    if (!quote) { lines.push(pending); pending = ''; }
    escape = false;
  }
  if (quote) throw new Error('Unterminated quoted value. Configuration may be incomplete.');
  return lines;
}

export function analyzeConfig(text: string): FeatureProfile {
  if (new TextEncoder().encode(text).length > 10 * 1024**2) throw new Error('Configuration exceeds 10 MiB.');
  if (text.includes('\0') || !/^\s*(?:#.*\n)*\s*config\s+/m.test(text)) throw new Error('Select an unencrypted plaintext FortiOS configuration backup.');
  const root: Block = { name: '', kind: 'config', settings: new Map(), children: [] };
  const stack = [root];
  for (const raw of logicalLines(text)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const [cmd, ...args] = tokens(line);
    const current = stack[stack.length - 1];
    if (cmd === 'config' || cmd === 'edit') {
      if (stack.length > 64 || !args.length) throw new Error('Invalid configuration nesting.');
      const child: Block = { name: cmd === 'config' ? args.join(' ') : '', kind: cmd, settings: new Map(), children: [] };
      current.children.push(child); stack.push(child);
    } else if (cmd === 'end' || cmd === 'next') {
      if (stack.length === 1 || current.kind !== (cmd === 'end' ? 'config' : 'edit')) throw new Error('Unbalanced configuration blocks.');
      stack.pop();
    } else if (cmd === 'set' || cmd === 'unset' || cmd === 'append') {
      if (!args.length) throw new Error('Invalid configuration setting.');
      if (cmd === 'unset') current.settings.delete(args[0]);
      else current.settings.set(args[0], args.slice(1));
    } else throw new Error('Unsupported configuration syntax. Export a FortiOS plaintext backup.');
  }
  if (stack.length !== 1) throw new Error('Configuration is incomplete: unclosed blocks.');
  const profile = emptyProfile();
  const record = (feature: FeatureName, state: FeatureState) => {
    if (state === 'configured' || profile[feature] === 'unknown') profile[feature] = state;
  };
  const get = (b: Block, key: string) => b.settings.get(key)?.[0];
  function visit(b: Block) {
    for (const feature of FEATURES) {
      if (!paths[feature].test(b.name)) continue;
      let state: FeatureState = 'unknown';
      const edits = b.children.filter(c => c.kind === 'edit');
      if (get(b, 'status') === 'disable') state = 'disabled';
      else if (feature === 'HA') state = ['a-p', 'a-a'].includes(get(b, 'mode') ?? '') ? 'configured' : get(b, 'mode') === 'standalone' ? 'disabled' : 'unknown';
      else if (feature === 'VDOMs') state = edits.length ? 'configured' : 'unknown';
      else if (feature === 'IPsec VPN') state = edits.some(e => get(e, 'status') !== 'disable') ? 'configured' : edits.length ? 'disabled' : 'unknown';
      else if (feature === 'Security profiles') state = 'unknown'; // Definitions alone do not establish policy use.
      else if (feature === 'BGP') state = get(b, 'as') && get(b, 'as') !== '0' ? 'configured' : 'unknown';
      else if (feature === 'OSPF') state = b.children.some(c => /^(network|area|ospf-interface|ospf6-interface)$/.test(c.name) && c.children.length) ? 'configured' : 'unknown';
      else if (feature === 'SD-WAN') state = get(b, 'status') === 'enable' || b.children.some(c => c.name === 'members' && c.children.some(e => get(e, 'status') !== 'disable')) ? 'configured' : 'unknown';
      else if (feature === 'SSL VPN') state = get(b, 'status') === 'enable' || !!get(b, 'source-interface') ? 'configured' : 'unknown';
      record(feature, state);
    }
    if (b.name === 'firewall policy' || b.name === 'firewall policy6') {
      const policies = b.children.filter(c => c.kind === 'edit');
      if (policies.some(p => get(p, 'status') !== 'disable' && get(p, 'utm-status') === 'enable' && ['av-profile', 'webfilter-profile', 'dnsfilter-profile', 'ips-sensor', 'application-list', 'profile-group'].some(k => !!get(p, k)))) record('Security profiles', 'configured');
    }
    if (b.name === 'system global' && get(b, 'vdom-mode')) record('VDOMs', get(b, 'vdom-mode') === 'no-vdom' ? 'disabled' : 'configured');
    b.children.forEach(visit);
  }
  visit(root);
  return profile;
}

const keywords: Record<FeatureName, RegExp> = {
  'SD-WAN': /\bsd[ -]?wan\b|virtual-wan-link/i,
  'IPsec VPN': /\bipsec\b|\bikev?[12]?\b/i,
  'SSL VPN': /\bssl[ -]?vpn\b/i,
  'BGP': /\bbgp\b/i, 'OSPF': /\bospfv?[236]?\b/i,
  'HA': /\bhigh availability\b|\bha\b|\bfgcp\b/i,
  'VDOMs': /\bvdoms?\b|\bvirtual domains?\b/i,
  'Security profiles': /\b(antivirus|web filter|webfilter|dns filter|dnsfilter|ips|application control|security profiles?)\b/i,
};
export function relevance(text: string, profile?: FeatureProfile): string[] {
  return profile ? FEATURES.filter(f => profile[f] === 'configured' && keywords[f].test(text)).map(f => `${f}: configuration detected; note mentions this feature (rules ${RULE_VERSION}).`) : [];
}
