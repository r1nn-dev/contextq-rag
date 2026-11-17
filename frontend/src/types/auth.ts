// docs/specs/api-spec.md > 1. 인증

export type Role = 'ROLE_USER' | 'ROLE_ADMIN'

export interface Credentials {
  email: string
  password: string
}

export interface TokenResponse {
  accessToken: string
  tokenType: 'Bearer'
  expiresIn: number
}

export interface SignupResponse {
  userId: number
}

export interface Me {
  userId: number
  email: string
  role: Role
  createdAt: string
}

/** Account rules (policy §1.1). Returns field → reason; empty when valid. */
export function validateCredentials(
  email: string,
  password: string,
  confirm: string | null = null,
): Record<string, string> {
  const errors: Record<string, string> = {}
  const normalized = email.trim().toLowerCase()
  const at = normalized.split('@')
  if (normalized.length === 0) {
    errors.email = '이메일을 입력해주세요.'
  } else if (normalized.length > 254 || at.length !== 2 || at[0] === '' || !at[1].includes('.')) {
    errors.email = '올바른 이메일 형식이 아닙니다.'
  }
  if (password.length < 8 || password.length > 64 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
    errors.password = '8~64자, 영문·숫자 각 1자 이상이어야 합니다.'
  } else if (password === normalized || password === email) {
    errors.password = '비밀번호는 이메일과 같을 수 없습니다.'
  }
  if (confirm !== null && confirm !== password) {
    errors.confirm = '비밀번호가 일치하지 않습니다.'
  }
  return errors
}
