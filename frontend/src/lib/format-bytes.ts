const byteUnits = ["Б", "КБ", "МБ", "ГБ", "ТБ", "ПБ"]

export function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0 Б"
  const unitIndex = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    byteUnits.length - 1,
  )
  const amount = value / 1024 ** unitIndex
  return `${new Intl.NumberFormat("ru", { maximumFractionDigits: amount >= 10 ? 1 : 2 }).format(amount)} ${byteUnits[unitIndex]}`
}
