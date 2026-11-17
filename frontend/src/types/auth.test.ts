import { describe, expect, it } from 'vitest'
import { validateCredentials } from './auth'

// policy §1.1 계정 규칙
describe('validateCredentials', () => {
  it('accepts a valid account', () => {
    expect(validateCredentials('user@example.com', 'pass1234', 'pass1234')).toEqual({})
  })

  it('normalizes the email before checking', () => {
    expect(validateCredentials('  User@Example.com ', 'pass1234')).toEqual({})
  })

  it('rejects emails without exactly one @ or without a dot in the domain', () => {
    expect(validateCredentials('user.example.com', 'pass1234').email).toBeDefined()
    expect(validateCredentials('a@b@example.com', 'pass1234').email).toBeDefined()
    expect(validateCredentials('user@localhost', 'pass1234').email).toBeDefined()
  })

  it('rejects emails over 254 characters', () => {
    expect(validateCredentials(`${'a'.repeat(250)}@x.io`, 'pass1234').email).toBeDefined()
  })

  it('requires 8~64 characters with at least one letter and one digit', () => {
    expect(validateCredentials('user@example.com', 'pass123').password).toBeDefined()
    expect(validateCredentials('user@example.com', 'password').password).toBeDefined()
    expect(validateCredentials('user@example.com', '12345678').password).toBeDefined()
    expect(validateCredentials('user@example.com', `a1${'x'.repeat(63)}`).password).toBeDefined()
  })

  it('rejects a password equal to the email', () => {
    expect(validateCredentials('user1@example.com', 'user1@example.com').password).toBeDefined()
  })

  it('checks the confirmation only when given', () => {
    expect(validateCredentials('user@example.com', 'pass1234', 'pass12345').confirm).toBeDefined()
    expect(validateCredentials('user@example.com', 'pass1234').confirm).toBeUndefined()
  })
})
