import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const root = path.resolve(process.argv[2] || '.');
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8');
const fail = (message) => {
  console.error(`BEHAVIOR FAIL: ${message}`);
  process.exit(1);
};

const html = read('index.html');
const css = read('styles.css');
const javascript = read('script.js');

const productCards = html.match(/class=["'][^"']*\bproduct-card\b[^"']*["']/gi) || [];
if (productCards.length !== 3) {
  fail(`expected exactly 3 product-card elements; found ${productCards.length}`);
}
if (!/id=["']theme-toggle["']/i.test(html)) {
  fail('index.html has no element with id="theme-toggle"');
}
if (!/(?:^|[\s,}])(?:body\s*)?\.dark-theme\b/m.test(css)) {
  fail('styles.css does not contain a .dark-theme selector');
}

class ClassList {
  constructor(initial = []) { this.values = new Set(initial); }
  add(...names) { names.forEach((name) => this.values.add(name)); }
  remove(...names) { names.forEach((name) => this.values.delete(name)); }
  contains(name) { return this.values.has(name); }
  toggle(name, force) {
    const enabled = force === undefined ? !this.contains(name) : Boolean(force);
    if (enabled) this.add(name); else this.remove(name);
    return enabled;
  }
}

const buttonListeners = new Map();
const documentListeners = new Map();
const button = {
  classList: new ClassList(),
  textContent: '',
  innerText: '',
  setAttribute() {},
  addEventListener(type, callback) { buttonListeners.set(type, callback); },
};
const body = { classList: new ClassList() };
const document = {
  body,
  documentElement: { classList: new ClassList(), setAttribute() {} },
  getElementById(id) { return id === 'theme-toggle' ? button : null; },
  querySelector(selector) {
    return selector.includes('theme-toggle') ? button : null;
  },
  querySelectorAll(selector) {
    if (selector.includes('product-card')) return Array.from({ length: 3 }, () => ({}));
    return [];
  },
  addEventListener(type, callback) { documentListeners.set(type, callback); },
};
const storage = new Map();
const localStorage = {
  getItem(key) { return storage.get(key) ?? null; },
  setItem(key, value) { storage.set(key, String(value)); },
  removeItem(key) { storage.delete(key); },
};
const sandbox = {
  document,
  localStorage,
  console,
  matchMedia() {
    return {
      matches: false,
      media: '(prefers-color-scheme: dark)',
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
    };
  },
  setTimeout: (callback) => { callback(); return 1; },
  clearTimeout() {},
};
sandbox.window = sandbox;

try {
  vm.runInNewContext(javascript, sandbox, { filename: 'script.js', timeout: 2000 });
  documentListeners.get('DOMContentLoaded')?.();
} catch (error) {
  fail(`script.js threw during startup: ${error.message}`);
}

const click = buttonListeners.get('click');
if (typeof click !== 'function') {
  fail('theme-toggle has no click handler');
}
const before = body.classList.contains('dark-theme');
try {
  click({ currentTarget: button, target: button, preventDefault() {} });
} catch (error) {
  fail(`theme-toggle click threw: ${error.message}`);
}
const after = body.classList.contains('dark-theme');
if (before === after) {
  fail('clicking theme-toggle did not toggle dark-theme on document.body');
}

console.log('BEHAVIOR PASS: product cards and dark-theme toggle work');
