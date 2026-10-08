// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Book, Change, Pairing, PulledChange } from './types'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Normalise what a person types into a hub base URL (rule R1: never assume same origin). */
export function normalizeHubUrl(input: string): string {
  let url = input.trim()
  if (!/^https?:\/\//i.test(url)) url = `http://${url}`
  return url.replace(/\/+$/, '')
}

async function request(pairing: Pick<Pairing, 'hubUrl' | 'token'> | { hubUrl: string },
                       path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  if ('token' in pairing) headers.set('Authorization', `Bearer ${pairing.token}`)
  let response: Response
  try {
    response = await fetch(`${pairing.hubUrl}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, 'The hub is unreachable')
  }
  if (!response.ok) {
    let message = response.statusText
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, message)
  }
  return response
}

export async function pair(hubUrl: string, code: string, deviceName: string) {
  const response = await request({ hubUrl }, '/pair', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, device_name: deviceName }),
  })
  return (await response.json()) as { device_id: string; token: string }
}

export async function health(hubUrl: string) {
  return (await (await request({ hubUrl }, '/health')).json()) as {
    ok: boolean; version: string; search_ready: boolean; vault_enabled: boolean; vault_ok: boolean
  }
}

export async function uploadBook(pairing: Pairing, file: File): Promise<Book> {
  // Raw body, not multipart: the hub checks the token before reading any of it.
  const response = await request(pairing, `/books?filename=${encodeURIComponent(file.name)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
  })
  return response.json()
}

export async function fetchBookFile(pairing: Pairing, bookId: string): Promise<Blob> {
  return (await request(pairing, `/books/${bookId}/file`)).blob()
}

export async function fetchCover(pairing: Pairing, bookId: string): Promise<Blob> {
  return (await request(pairing, `/books/${bookId}/cover`)).blob()
}

export async function pushChanges(pairing: Pairing, changes: Change[], keepalive = false) {
  const response = await request(pairing, '/sync/push', {
    method: 'POST',
    keepalive,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ changes }),
  })
  return (await response.json()) as {
    results: { index: number; status: 'accepted' | 'ignored' | 'rejected'; reason?: string }[]
  }
}

export async function pullChanges(pairing: Pairing, since: number) {
  const response = await request(pairing, `/sync/pull?since=${since}&limit=500`)
  return (await response.json()) as { changes: PulledChange[]; cursor: number; more: boolean
                                       latest: number }
}

export interface Invite { code: string; display: string; url: string; qr_svg: string
                         expires_at: string }

/** A one-time code (with link and QR) that pairs one more device. */
export async function createInvite(pairing: Pairing): Promise<Invite> {
  return (await request(pairing, '/pairing-codes', { method: 'POST' })).json()
}

export interface Device { id: string; name: string; paired_at: string; last_seen: string
                          current: boolean }

export async function listDevices(pairing: Pairing): Promise<Device[]> {
  return (await request(pairing, '/devices')).json()
}

export async function revokeDevice(pairing: Pairing, deviceId: string): Promise<void> {
  await request(pairing, `/devices/${deviceId}`, { method: 'DELETE' })
}
