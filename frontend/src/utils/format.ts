// Display formatting. Server times are ISO 8601 UTC (api-spec 0.1); shown in local time.

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function formatDate(iso: string): string {
  return formatDateTime(iso).slice(0, 10)
}

export function formatRelative(iso: string, now: number = Date.now()): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const minutes = Math.floor((now - t) / 60_000)
  if (minutes < 1) return '방금 전'
  if (minutes < 60) return `${minutes}분 전`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}시간 전`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}일 전`
  return formatDate(iso)
}

export function formatNumber(n: number): string {
  return n.toLocaleString('ko-KR')
}
