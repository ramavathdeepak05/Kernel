{{- define "cp.fullname" -}}
{{- printf "%s-%s" .Release.Name "control-plane" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "cp.labels" -}}
app.kubernetes.io/name: alis-control-plane
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.global.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "cp.selectorLabels" -}}
app.kubernetes.io/name: alis-control-plane
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "cp.image" -}}
{{- printf "%s:%s" .Values.global.image.repository (.Values.global.image.tag | default .Chart.AppVersion) }}
{{- end }}

{{- define "cp.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "cp.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
