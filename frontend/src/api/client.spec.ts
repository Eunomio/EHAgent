import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from './client'

describe('local API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('parses the typed health response', async () => {
    const payload = {
      status: 'ok',
      version: '0.2.0',
      environment: 'test',
      database: 'ok',
      runtime_mode: 'UNINITIALIZED',
      checked_at: '2026-08-11T00:00:00Z',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    await expect(api.health()).resolves.toEqual(payload)
  })

  it('rejects non-success responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('offline', { status: 503 })))
    await expect(api.health()).rejects.toThrow('offline')
  })
})
