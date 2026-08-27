{{- define "acde.name" -}}
acde
{{- end -}}

{{- define "acde.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "acde.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "acde.labels" -}}
app.kubernetes.io/name: {{ include "acde.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "acde.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{ .Values.secrets.existingSecret }}
{{- else -}}
{{ include "acde.fullname" . }}-secrets
{{- end -}}
{{- end -}}

{{/*
Shared environment for both acde-server and acde-loop — every value either comes from the Secret
(never inlined into a Deployment spec, which would otherwise put a credential in `kubectl get
pod -o yaml` output) or is genuinely non-secret config.
*/}}
{{- define "acde.commonEnv" -}}
- name: POSTGRES_HOST
  value: {{ required "postgres.host is required (bring your own managed Postgres)" .Values.postgres.host | quote }}
- name: POSTGRES_PORT
  value: {{ .Values.postgres.port | quote }}
- name: POSTGRES_DB
  value: {{ .Values.postgres.db | quote }}
- name: POSTGRES_USER
  value: {{ .Values.postgres.user | quote }}
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ if .Values.postgres.existingSecret }}{{ .Values.postgres.existingSecret }}{{ else }}{{ include "acde.secretName" . }}{{ end }}
      key: {{ .Values.postgres.existingSecretPasswordKey }}
- name: OPA_URL
  value: "http://{{ include "acde.fullname" . }}-opa:8181"
- name: AIRFLOW_URL
  value: {{ .Values.airflowUrl | quote }}
- name: AIRFLOW_USER
  value: {{ .Values.airflowUser | quote }}
- name: AIRFLOW_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "acde.secretName" . }}
      key: airflow-password
- name: ACDE_MODE
  value: {{ .Values.acdeMode | quote }}
- name: LLM_PROVIDER
  value: {{ .Values.llmProvider | quote }}
- name: MOCK_LLM
  value: {{ .Values.mockLlm | quote }}
- name: API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "acde.secretName" . }}
      key: api-key
- name: OAI_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "acde.secretName" . }}
      key: oai-api-key
- name: ANTHROPIC_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "acde.secretName" . }}
      key: anthropic-api-key
- name: GEMINI_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "acde.secretName" . }}
      key: gemini-api-key
{{- range $k, $v := .Values.extraEnv }}
- name: {{ $k }}
  value: {{ $v | quote }}
{{- end }}
{{- end -}}
