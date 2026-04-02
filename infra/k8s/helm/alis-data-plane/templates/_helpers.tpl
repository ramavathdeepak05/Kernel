{{/*
Expand the name of the chart.
*/}}
{{- define "alis.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "alis.fullname" -}}
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
Chart label.
*/}}
{{- define "alis.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "alis.labels" -}}
helm.sh/chart: {{ include "alis.chart" . }}
{{ include "alis.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.global.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.global.labels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "alis.selectorLabels" -}}
app.kubernetes.io/name: {{ include "alis.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "alis.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "alis.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Namespace to deploy into.
*/}}
{{- define "alis.namespace" -}}
{{- default .Release.Namespace .Values.global.namespace }}
{{- end }}

{{/*
Image reference.
*/}}
{{- define "alis.image" -}}
{{- printf "%s:%s" .Values.global.image.repository (.Values.global.image.tag | default .Chart.AppVersion) }}
{{- end }}

{{/*
Common environment variables (shared by app, worker, beat).
Secrets are mounted from the external secret; plain config from configmap.
*/}}
{{- define "alis.env" -}}
- name: APP_ENV
  valueFrom:
    configMapKeyRef:
      name: {{ include "alis.fullname" . }}-config
      key: APP_ENV
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "alis.fullname" . }}-secrets
      key: DATABASE_URL
- name: REDIS_URL
  valueFrom:
    configMapKeyRef:
      name: {{ include "alis.fullname" . }}-config
      key: REDIS_URL
- name: CONTROL_PLANE_URL
  valueFrom:
    configMapKeyRef:
      name: {{ include "alis.fullname" . }}-config
      key: CONTROL_PLANE_URL
- name: CONTROL_PLANE_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ include "alis.fullname" . }}-secrets
      key: CONTROL_PLANE_TOKEN
- name: AI_SERVICE_URL
  valueFrom:
    configMapKeyRef:
      name: {{ include "alis.fullname" . }}-config
      key: AI_SERVICE_URL
- name: AI_SERVICE_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ include "alis.fullname" . }}-secrets
      key: AI_SERVICE_TOKEN
- name: S3_ENDPOINT_URL
  valueFrom:
    configMapKeyRef:
      name: {{ include "alis.fullname" . }}-config
      key: S3_ENDPOINT_URL
- name: S3_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "alis.fullname" . }}-secrets
      key: S3_ACCESS_KEY
- name: S3_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "alis.fullname" . }}-secrets
      key: S3_SECRET_KEY
- name: SAAS_DOMAIN_SUFFIX
  valueFrom:
    configMapKeyRef:
      name: {{ include "alis.fullname" . }}-config
      key: SAAS_DOMAIN_SUFFIX
{{- with .Values.app.extraEnv }}
{{ toYaml . }}
{{- end }}
{{- end }}
