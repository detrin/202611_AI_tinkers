import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { isAvailable, itemName, itemSub, title } from './format'
import type { Item } from './types'

export function Sheet({ title: heading, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-label={heading} onClick={(e) => e.stopPropagation()}>
        <div className="sheet-head">
          <h2>{heading}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Photo({ src, alt }: { src: string | null; alt: string }) {
  return <div className="photo">{src ? <img src={src} alt={alt} loading="lazy" /> : <span>{alt}</span>}</div>
}

export function Availability({ item }: { item: Item }) {
  const ok = isAvailable(item)
  return (
    <span className={`avail ${ok ? 'ok' : 'off'}`}>
      <i />
      {ok ? 'Available' : title(item.availability)}
    </span>
  )
}

export function Notice({ kind = 'info', children }: { kind?: 'info' | 'error'; children: ReactNode }) {
  return <p className={`notice ${kind}`}>{children}</p>
}

/** Item details with the actions shared by Today and My Closet. */
export function ItemSheet({
  item,
  onClose,
  actions,
}: {
  item: Item
  onClose: () => void
  actions: ReactNode
}) {
  const rows: [string, string | null][] = [
    ['Category', title(item.category)],
    ['Colour', (item.colors || []).map(title).join(', ')],
    ['Pattern', title(item.pattern)],
    ['Material', title(item.material)],
    ['Fit', title(item.fit)],
    ['Warmth', item.warmth ? `${item.warmth} / 5` : null],
    ['Formality', item.formality ? `${item.formality} / 5` : null],
    ['Source', item.source_type === 'product_url' ? 'Product link' : title(item.source_type)],
  ]
  return (
    <Sheet title={itemName(item)} onClose={onClose}>
      <div className="item-detail">
        <Photo src={item.image_url} alt={itemName(item)} />
        <div>
          <p className="muted">{itemSub(item)}</p>
          <Availability item={item} />
          <dl>
            {rows
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
          </dl>
        </div>
      </div>
      <div className="stack">{actions}</div>
    </Sheet>
  )
}
