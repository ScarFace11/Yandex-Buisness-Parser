// Склейка частей стилей в порядке каскада для node-тестов.
//
// Части названы с двумя цифрами (00-…, 01-…), поэтому sorted() совпадает
// с порядком ссылок в templates/index.html. Отдельный список здесь не
// нужен: новый файл подхватится сам и не разойдётся с шаблоном.
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

export function readCss(root) {
  const dir = join(root, 'static', 'css');
  return readdirSync(dir)
    .filter(f => f.endsWith('.css'))
    .sort()
    .map(f => readFileSync(join(dir, f), 'utf8'))
    .join('\n');
}
