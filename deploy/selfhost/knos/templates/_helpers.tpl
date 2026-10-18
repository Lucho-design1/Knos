{{- define "knos.name" -}}{{ .Release.Name }}-knos{{- end -}}
{{- define "knos.labels" -}}
app.kubernetes.io/name: knos
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
{{- define "knos.selector" -}}
app.kubernetes.io/name: knos
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
