export interface Resource {
  id: string
  apiVersion: string
  kind: string
  metadata: {
    name: string
    namespace: string
    labels: Record<string, string>
  }
  spec: Record<string, unknown>
  version: number
  created_at: string
  updated_at: string
}
