// Auth mocks (docs/specs/api-spec.md > 1).
// Seeded accounts admin@contextq.dev / user@example.com accept any well-formed password
// except "wrongpass1", which fails so the lock path (5 failures) can be tried.

import { isRecord } from '@/types/api'
import { validateCredentials, type Me } from '@/types/auth'
import { fail, ok, route, type MockRequest } from '../router'
import { ACCESS_TTL_MS, mockState, userById, type MockUser } from '../state'

const LOCK_MS = 15 * 60_000

function issueToken(user: MockUser) {
  const token = `mock.${crypto.randomUUID()}`
  mockState.accessTokens.set(token, { userId: user.userId, expiresAt: Date.now() + ACCESS_TTL_MS })
  mockState.refreshUserId = user.userId
  return { accessToken: token, tokenType: 'Bearer', expiresIn: ACCESS_TTL_MS / 1000 }
}

export type AuthResult =
  | { kind: 'guest' }
  | { kind: 'user'; user: MockUser }
  | { kind: 'error'; response: Response }

/** Resolves the caller from the Authorization header, like the backend's JWT filter. */
export function authenticate(req: MockRequest): AuthResult {
  const header = req.headers.get('Authorization')
  if (header === null) return { kind: 'guest' }
  const entry = mockState.accessTokens.get(header.replace(/^Bearer /, ''))
  if (entry === undefined) {
    return { kind: 'error', response: fail('AUTH_TOKEN_INVALID', '인증 정보가 올바르지 않습니다.', 401) }
  }
  if (entry.expiresAt < Date.now()) {
    return { kind: 'error', response: fail('AUTH_TOKEN_EXPIRED', '로그인이 만료되었습니다.', 401) }
  }
  const user = userById(entry.userId)
  return user === null
    ? { kind: 'error', response: fail('AUTH_TOKEN_INVALID', '인증 정보가 올바르지 않습니다.', 401) }
    : { kind: 'user', user }
}

function credentialsOf(req: MockRequest): { email: string; password: string } {
  const body = isRecord(req.body) ? req.body : {}
  return {
    email: typeof body.email === 'string' ? body.email.trim().toLowerCase() : '',
    password: typeof body.password === 'string' ? body.password : '',
  }
}

route('POST', '/auth/signup', (req) => {
  const { email, password } = credentialsOf(req)
  const errors = validateCredentials(email, password)
  if (mockState.users.has(email)) errors.email = '이미 사용 중인 이메일입니다.'
  const details = Object.entries(errors).map(([field, reason]) => ({ field, reason }))
  if (details.length > 0) return fail('INVALID_REQUEST', '입력값을 확인해주세요.', 400, { details })
  const user: MockUser = {
    userId: mockState.nextUserId++,
    email,
    password,
    role: 'ROLE_USER',
    createdAt: new Date().toISOString(),
    failures: 0,
    lockedUntil: 0,
  }
  mockState.users.set(email, user)
  return ok({ userId: user.userId }, 201, '회원가입이 완료되었습니다.')
})

route('POST', '/auth/login', (req) => {
  const { email, password } = credentialsOf(req)
  if (email === '' || password === '') {
    return fail('INVALID_REQUEST', '입력값을 확인해주세요.', 400)
  }
  const user = mockState.users.get(email)
  if (user !== undefined && user.lockedUntil > Date.now()) {
    const retry = Math.ceil((user.lockedUntil - Date.now()) / 1000)
    return fail('AUTH_LOCKED', '로그인 시도 초과. 15분 후 다시 시도해주세요.', 429, { retryAfterSec: retry })
  }
  const matches =
    user !== undefined && (user.password === null ? password !== 'wrongpass1' : user.password === password)
  if (!matches) {
    if (user !== undefined) {
      user.failures += 1
      if (user.failures >= 5) {
        user.failures = 0
        user.lockedUntil = Date.now() + LOCK_MS
        return fail('AUTH_LOCKED', '로그인 시도 초과. 15분 후 다시 시도해주세요.', 429, { retryAfterSec: LOCK_MS / 1000 })
      }
    }
    return fail('AUTH_INVALID_CREDENTIALS', '이메일 또는 비밀번호가 올바르지 않습니다.', 401)
  }
  user.failures = 0
  return ok(issueToken(user))
})

route('POST', '/auth/refresh', () => {
  const user = mockState.refreshUserId === null ? null : userById(mockState.refreshUserId)
  if (user === null) return fail('AUTH_REFRESH_MISSING', '로그인이 필요합니다.', 401)
  return ok(issueToken(user))
})

route('POST', '/auth/logout', () => {
  mockState.refreshUserId = null
  return ok(null, 200, '로그아웃되었습니다.')
})

route('GET', '/auth/me', (req) => {
  const auth = authenticate(req)
  if (auth.kind === 'error') return auth.response
  if (auth.kind === 'guest') return fail('AUTH_TOKEN_MISSING', '로그인이 필요합니다.', 401)
  const me: Me = {
    userId: auth.user.userId,
    email: auth.user.email,
    role: auth.user.role,
    createdAt: auth.user.createdAt,
  }
  return ok(me)
})
