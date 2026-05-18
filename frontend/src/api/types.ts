/**
 * Re-exported API types from the auto-generated OpenAPI schema.
 *
 * Regenerate with: bun run generate:api
 * Source: openapi.json (fetched from running server at /openapi.json)
 */

import type { components } from './schema'

// ── Response types ──────────────────────────────────────────────────────────

export type HealthResponse = components['schemas']['HealthResponse']
export type ReadinessResponse = components['schemas']['ReadinessResponse']
export type ComponentCheck = components['schemas']['ComponentCheck']

export type ResourceResponse = components['schemas']['ResourceResponse']
export type ResourceListResponse = components['schemas']['ResourceListResponse']

export type ExecutionResponse = components['schemas']['ExecutionResponse']
export type ExecutionListResponse = components['schemas']['ExecutionListResponse']
export type ExecutionTaskResponse = components['schemas']['ExecutionTaskResponse']
export type ExecutionEventItem = components['schemas']['ExecutionEventItem']
export type ExecutionEventsResponse = components['schemas']['ExecutionEventsResponse']

export type UserResponse = components['schemas']['UserResponse']
export type UserListResponse = components['schemas']['UserListResponse']
export type GroupResponse = components['schemas']['GroupResponse']
export type GroupListResponse = components['schemas']['GroupListResponse']

export type AuthResponse = components['schemas']['AuthResponse']
export type TokenResponse = components['schemas']['TokenResponse']

export type AuditLogItem = components['schemas']['AuditLogItem']
export type AuditLogListResponse = components['schemas']['AuditLogListResponse']

// ── Request types ───────────────────────────────────────────────────────────

export type KickoffRequest = components['schemas']['KickoffRequest']
export type TrainRequest = components['schemas']['TrainRequest']
export type TestRequest = components['schemas']['TestRequest']
export type RegisterRequest = components['schemas']['RegisterRequest']
export type LoginRequest = components['schemas']['LoginRequest']
export type RefreshRequest = components['schemas']['RefreshRequest']
