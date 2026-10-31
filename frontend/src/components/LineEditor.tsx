import { Plus, Trash2 } from 'lucide-react'
import { inr } from '../lib/format'
import { useApi } from '../lib/hooks'
import type { Page, Product } from '../lib/types'
import { Button } from './ui'

export interface EditLine { product_id: number | ''; variant_id: number | ''; quantity: number; unit_price: string }
export const emptyLine = (): EditLine => ({ product_id: '', variant_id: '', quantity: 1, unit_price: '' })

export function useProducts() {
  return useApi<Page<Product>>('/products', { active: true, page_size: 200 })
}

export function catalogPrice(products: Product[] | undefined, l: EditLine): number {
  const p = products?.find((x) => x.id === l.product_id)
  if (!p) return 0
  const v = p.variants.find((x) => x.id === l.variant_id)
  return Number(p.sales_price) + Number(v?.price_extra ?? 0)
}

/** Product / variant / quantity / price rows. Shows the catalog price (product + variant adjustment) live. */
export function LineEditor({ lines, onChange, minQty = 1, allowPrice = true }: { lines: EditLine[]; onChange: (l: EditLine[]) => void; minQty?: number; allowPrice?: boolean }) {
  const { data } = useProducts()
  const products = data?.items
  const upd = (i: number, patch: Partial<EditLine>) => onChange(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const total = lines.reduce((s, l) => s + (l.unit_price !== '' ? Number(l.unit_price) : catalogPrice(products, l)) * (l.quantity || 0), 0)
  return (
    <div className="space-y-2">
      <div className="hidden grid-cols-[2fr_1.4fr_80px_120px_100px_32px] gap-2 px-1 text-[11px] font-bold uppercase tracking-wider text-ink-faint md:grid">
        <span>Product</span><span>Variant</span><span>Qty</span><span>{allowPrice ? 'Unit price' : ''}</span><span className="text-right">Amount</span><span />
      </div>
      {lines.map((l, i) => {
        const p = products?.find((x) => x.id === l.product_id)
        const cat = catalogPrice(products, l)
        const price = l.unit_price !== '' ? Number(l.unit_price) : cat
        return (
          <div key={i} className="grid grid-cols-2 gap-2 rounded-lg border border-line p-2 md:grid-cols-[2fr_1.4fr_80px_120px_100px_32px] md:border-0 md:p-0">
            <select className="input col-span-2 md:col-span-1" value={l.product_id} onChange={(e) => upd(i, { product_id: Number(e.target.value) || '', variant_id: '' })} aria-label="Product">
              <option value="">Select product…</option>
              {products?.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select>
            <select className="input" value={l.variant_id} disabled={!p?.variants.filter((v) => v.is_active).length} onChange={(e) => upd(i, { variant_id: Number(e.target.value) || '' })} aria-label="Variant">
              <option value="">{p?.variants.length ? 'No variant' : '—'}</option>
              {p?.variants.filter((v) => v.is_active).map((v) => <option key={v.id} value={v.id}>{v.attribute}: {v.value}{Number(v.price_extra) ? ` (+${inr(v.price_extra)})` : ''}</option>)}
            </select>
            <input className="input" type="number" min={minQty} value={l.quantity} onChange={(e) => upd(i, { quantity: Number(e.target.value) })} aria-label="Quantity" />
            {allowPrice ? <input className="input num" type="number" min={0} step="0.01" placeholder={cat ? cat.toFixed(2) : 'Catalog'} value={l.unit_price} onChange={(e) => upd(i, { unit_price: e.target.value })} aria-label="Unit price override" title="Leave blank to use the catalog price" /> : <span />}
            <span className="flex items-center justify-end num font-semibold">{p ? inr(price * (l.quantity || 0)) : '—'}</span>
            <button type="button" onClick={() => onChange(lines.filter((_, j) => j !== i))} className="grid place-items-center rounded-md text-ink-faint hover:bg-brand-50 hover:text-bad" aria-label="Remove line"><Trash2 className="h-4 w-4" /></button>
          </div>
        )
      })}
      <div className="flex items-center justify-between pt-1">
        <Button type="button" size="sm" variant="ghost" icon={<Plus className="h-4 w-4" />} onClick={() => onChange([...lines, emptyLine()])}>Add line</Button>
        <span className="text-[13px] text-ink-soft">Subtotal (excl. tax) <b className="ml-2 num text-ink">{inr(total)}</b></span>
      </div>
      {lines.some((l) => l.quantity < minQty) && <p className="text-[12px] text-warn">This plan requires at least {minQty} per line.</p>}
    </div>
  )
}

export const toPayload = (lines: EditLine[]) => lines.filter((l) => l.product_id).map((l) => ({
  product_id: l.product_id, variant_id: l.variant_id || null, quantity: l.quantity, unit_price: l.unit_price === '' ? null : l.unit_price,
}))
