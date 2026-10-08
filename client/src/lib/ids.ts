// SPDX-License-Identifier: AGPL-3.0-or-later
const CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'

/** A ULID: 48-bit millisecond time + 80 random bits, 26 Crockford characters. */
export function ulid(now: number = Date.now()): string {
  let time = ''
  let t = now
  for (let i = 0; i < 10; i++) {
    time = CROCKFORD[t % 32] + time
    t = Math.floor(t / 32)
  }
  const random = crypto.getRandomValues(new Uint8Array(16))
  let rest = ''
  for (let i = 0; i < 16; i++) rest += CROCKFORD[random[i] % 32]
  return time + rest
}

/** UTC timestamp in the hub's fixed format, YYYY-MM-DDTHH:MM:SS.mmmZ. */
export function utcNow(date: Date = new Date()): string {
  return date.toISOString()
}
