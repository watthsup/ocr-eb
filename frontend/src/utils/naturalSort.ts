/** Natural (numeric-aware) filename ordering: page_1, page_2, page_2_cont, page_10. */
export function naturalCompare(a: string, b: string): number {
  const re = /(\d+)/g;
  const aChunks = a.split(re);
  const bChunks = b.split(re);
  const len = Math.max(aChunks.length, bChunks.length);
  for (let i = 0; i < len; i++) {
    const ac = aChunks[i];
    const bc = bChunks[i];
    if (ac === undefined) return -1;
    if (bc === undefined) return 1;
    if (ac === bc) continue;
    const aIsNum = /^\d+$/.test(ac);
    const bIsNum = /^\d+$/.test(bc);
    if (aIsNum && bIsNum) {
      const an = Number(ac);
      const bn = Number(bc);
      if (an !== bn) return an - bn;
      if (ac.length !== bc.length) return ac.length - bc.length;
    } else {
      const aLower = ac.toLowerCase();
      const bLower = bc.toLowerCase();
      if (aLower !== bLower) {
        return aLower < bLower ? -1 : 1;
      }
      if (ac !== bc) {
        return ac < bc ? -1 : 1;
      }
    }
  }
  return 0;
}

export function naturalSortBy<T>(items: readonly T[], key: (item: T) => string): T[] {
  return [...items].sort((a, b) => naturalCompare(key(a), key(b)));
}

/** Generic comparator for mixed cell values used by sortable grids. */
export function compareValues(a: unknown, b: unknown): number {
  const aNull = a === null || a === undefined || a === '';
  const bNull = b === null || b === undefined || b === '';
  if (aNull && bNull) return 0;
  if (aNull) return 1; // empties sink to the bottom
  if (bNull) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  const an = typeof a === 'string' ? Number(a.replace(/,/g, '')) : NaN;
  const bn = typeof b === 'string' ? Number(b.replace(/,/g, '')) : NaN;
  if (!Number.isNaN(an) && !Number.isNaN(bn) && a !== '' && b !== '') return an - bn;
  return naturalCompare(String(a), String(b));
}
