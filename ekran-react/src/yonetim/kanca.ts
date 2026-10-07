import { useEffect, useState } from "react"

/** Degeri `ms` sonra yansitir: her tusta sunucuya istek gitmesin. */
export function useGecikmeli<T>(deger: T, ms = 300): T {
  const [gecikmeli, setGecikmeli] = useState(deger)
  useEffect(() => {
    const zamanlayici = window.setTimeout(() => setGecikmeli(deger), ms)
    return () => window.clearTimeout(zamanlayici)
  }, [deger, ms])
  return gecikmeli
}
