/** Profil fotografi adresi; surum degisince tarayici yenisini alir (sunucu bu adresi bir gun saklatir). */
export const fotoAdresi = (surum: number) => `/api/v1/session/photo?v=${surum}`

/** Secilen resmi ortadan kare kirpip 256 px JPEG'e cevirir: sunucu yalniz JPEG kabul eder, telefon fotografi da kuculur. */
export async function kareJpeg(dosya: Blob, boyut = 256): Promise<Blob> {
  const resim = await createImageBitmap(dosya)
  const kenar = Math.min(resim.width, resim.height)
  const tuval = document.createElement("canvas")
  tuval.width = boyut
  tuval.height = boyut
  const ciz = tuval.getContext("2d")
  if (!ciz) throw new Error("canvas")
  ciz.drawImage(resim, (resim.width - kenar) / 2, (resim.height - kenar) / 2, kenar, kenar, 0, 0, boyut, boyut)
  resim.close()
  return new Promise((coz, red) => tuval.toBlob((b) => (b ? coz(b) : red(new Error("jpeg"))), "image/jpeg", 0.88))
}
