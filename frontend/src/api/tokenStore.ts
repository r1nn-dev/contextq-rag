// Access Token lives in module memory only (policy §1.2 "메모리에만 보관").
// A reload drops it; the HttpOnly refresh cookie restores the session.

let accessToken: string | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}
