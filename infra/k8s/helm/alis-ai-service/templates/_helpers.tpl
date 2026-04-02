{{- define "ai.fullname" -}}
{{- printf "%s-%s" .Release.Name "ai-service" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "ai.labels" -}}
app.kubernetes.io/name: alis-ai-service
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.global.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "ai.selectorLabels" -}}
app.kubernetes.io/name: alis-ai-service
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "ai.image" -}}
{{- printf "%s:%s" .Values.global.image.repository (.Values.global.image.tag | default .Chart.AppVersion) }}
{{- end }}

{{- define "ai.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "ai.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
