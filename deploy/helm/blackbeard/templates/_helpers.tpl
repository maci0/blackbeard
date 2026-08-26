{{/*
Expand the name of the chart.
*/}}
{{- define "blackbeard.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "blackbeard.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "blackbeard.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "blackbeard.labels" -}}
helm.sh/chart: {{ include "blackbeard.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: blackbeard
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- if .Values.commonLabels }}
{{ toYaml .Values.commonLabels }}
{{- end }}
{{- end }}

{{/*
Selector labels for a component.
Usage: {{ include "blackbeard.selectorLabels" (dict "context" . "component" "api") }}
*/}}
{{- define "blackbeard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "blackbeard.name" .context }}
app.kubernetes.io/instance: {{ .context.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
API image reference
*/}}
{{- define "blackbeard.apiImage" -}}
{{ .Values.api.image.repository }}:{{ .Values.api.image.tag | default .Chart.AppVersion }}
{{- end }}

{{/*
UI image reference
*/}}
{{- define "blackbeard.uiImage" -}}
{{ .Values.ui.image.repository }}:{{ .Values.ui.image.tag | default .Chart.AppVersion }}
{{- end }}

{{/*
Secrets name: chart-managed Secret, or an external one via existingSecret.
*/}}
{{- define "blackbeard.secretsName" -}}
{{- if .Values.existingSecret -}}
{{- .Values.existingSecret -}}
{{- else -}}
{{- include "blackbeard.fullname" . }}-secrets
{{- end -}}
{{- end }}

{{/*
ConfigMap name
*/}}
{{- define "blackbeard.configmapName" -}}
{{ include "blackbeard.fullname" . }}-config
{{- end }}

{{/*
PostgreSQL host
*/}}
{{- define "blackbeard.postgresHost" -}}
{{ include "blackbeard.fullname" . }}-postgres
{{- end }}

{{/*
Valkey host
*/}}
{{- define "blackbeard.valkeyHost" -}}
{{ include "blackbeard.fullname" . }}-valkey
{{- end }}

{{/*
LiteLLM host
*/}}
{{- define "blackbeard.litellmHost" -}}
{{ include "blackbeard.fullname" . }}-litellm
{{- end }}

{{/*
Database URL for the API (asyncpg).
WARNING: $(DATABASE_PASSWORD) is interpolated by Kubernetes at runtime without
URL-encoding. Passwords containing @ : / ? # % or other URL-special characters
will break the DSN. Use only alphanumeric + hyphen + underscore in passwords.
*/}}
{{- define "blackbeard.databaseUrl" -}}
postgresql+asyncpg://{{ .Values.database.user }}:$(DATABASE_PASSWORD)@{{ include "blackbeard.postgresHost" . }}:{{ .Values.postgres.service.port }}/{{ .Values.database.name }}
{{- end }}

{{/*
Database URL for LiteLLM (psycopg2 / sync)
*/}}
{{- define "blackbeard.litellmDatabaseUrl" -}}
postgresql://{{ .Values.database.user }}:$(DATABASE_PASSWORD)@{{ include "blackbeard.postgresHost" . }}:{{ .Values.postgres.service.port }}/litellm
{{- end }}

{{/*
Valkey URL
*/}}
{{- define "blackbeard.valkeyUrl" -}}
valkey://default:$(VALKEY_PASSWORD)@{{ include "blackbeard.valkeyHost" . }}:{{ .Values.valkey.service.port }}/0
{{- end }}
