{{/*
Settings of the app for the templates of the library chart foca-common (see
`foca-common.checkSettings` and "Helm library chart" in FOCA's docs), as
YAML; the templates are called with a dict of the root context (`root`) and
these settings (`settings`). They follow the base config in the image
(`drs_filer/config.yaml`): no size limit of request bodies, no token issuers
and no access control (DRS-Filer has no authentication, so the library
requires neither an audience nor access control: `requireAudience` and
`requireAccessControl` are false), and its database (`db.dbs`). The
generated config sets the public URL of the app (`endpoints`, for the
`self_uri` and access URLs of objects) from `hostName`, with HTTPS on port
443, as TLS is usually terminated by the ingress, the route or a proxy in
front of the cluster. Every template includes the settings, so the app's
checks (`drs-filer.validate`) run first, before those of the library and
whichever template Helm renders first.
*/}}
{{- define "drs-filer.settings" -}}
{{- include "drs-filer.validate" . -}}
valuesKey: drsFiler
requireAudience: false
requireAccessControl: false
mongodb:
  databases: [drsStore]
config:
  endpoints:
    url_prefix: https
    external_host: {{ .Values.hostName | toJson }}
    external_port: 443
{{- end -}}

{{/*
Checks of the values and the release specific to this app; renders nothing.
Included by the settings (`drs-filer.settings`), so in every template, before
the library's checks (`foca-common.validate`); the checks of renamed and
removed values come first, so that they are reported instead of their
consequences (e.g., a missing `hostName` for `host_name`).
*/}}
{{- define "drs-filer.validate" -}}
{{- include "drs-filer.checkLegacyValues" . -}}
{{- $_ := required "hostName must be set to the public host name of the app (see deployment/README.md, Configuration)" .Values.hostName -}}
{{- end -}}

{{/*
Fails on values of the charts before foca-common, which the chart would
otherwise ignore; renders nothing.
*/}}
{{- define "drs-filer.checkLegacyValues" -}}
{{- $hint := "(see deployment/README.md, From earlier charts)" -}}
{{- /*
Keys renamed to camelCase, following Helm's conventions; the old keys would
otherwise be ignored
*/ -}}
{{- $renamed := dict
  "host_name" "host_name was renamed to hostName"
  "drs_filer" "drs_filer was renamed to drsFiler (drs_filer.ingress is drsFiler.ingress.enabled, drs_filer.appName is gone: names are derived from the release name)"
-}}
{{- range $old := keys $renamed | sortAlpha -}}
{{- if hasKey $.Values $old -}}
{{- fail (printf "%s (camelCase, following Helm conventions): rename it in the values file %s" (get $renamed $old) $hint) -}}
{{- end -}}
{{- end -}}
{{- if hasKey .Values "clusterType" -}}
{{- fail (printf "clusterType was removed: the chart creates an Ingress, an HTTPRoute (drsFiler.httpRoute) or, with drsFiler.ingress.enabled false, an OpenShift Route; remove it from the values file (see deployment/README.md, Exposing the app) %s" $hint) -}}
{{- end -}}
{{- if hasKey .Values "apiServer" -}}
{{- fail (printf "apiServer was removed with the config Job: the chart renders the config overlay itself; remove it from the values file %s" $hint) -}}
{{- end -}}
{{- $app := .Values.drsFiler -}}
{{- if kindIs "map" $app -}}
{{- $removed := dict
  "appName" "resource names are derived from the release name; set fullnameOverride to choose them at installation"
  "config" "the config overlay is the top-level value config"
-}}
{{- range $key := keys $removed | sortAlpha -}}
{{- if hasKey $app $key -}}
{{- fail (printf "drsFiler.%s was removed with the chart on foca-common: %s %s" $key (get $removed $key) $hint) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Fails on upgrades of releases of the charts before foca-common, whose
resources have other names and selectors: the upgrade would start the app on
a new, empty database (the old claim `mongodb` is not used), or fail on the
immutable selector of the app's Deployment, and on upgrades that rename
MongoDB, which would start it on a new, empty claim; renders nothing.
Releases are recognized by their Deployments (`drs-filer.failIfLegacy`; not
by claims, which uninstalling a release may keep). Included once (in the
app's ConfigMap template), as it looks up resources in the cluster. `lookup`
finds nothing in `helm template` and client-side dry runs.
*/}}
{{- define "drs-filer.checkUpgrade" -}}
{{- if .Release.IsUpgrade -}}
{{- $deployments := lookup "apps/v1" "Deployment" .Release.Namespace "" | default dict -}}
{{- range $resource := (get $deployments "items" | default list) -}}
{{- include "drs-filer.failIfLegacy" (dict "root" $ "resource" $resource) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Fails if a Deployment (looked up in the cluster) belongs to this release, but
was created by a chart before foca-common (without the label
`app.kubernetes.io/instance`), has another `app.kubernetes.io/name` label (a
changed `nameOverride`: the selectors of Deployments can't be changed, while
those of Services would be), or is the release's MongoDB under another name
(a changed `fullnameOverride` or `nameOverride`), which would start MongoDB
on a new, empty claim (unless the claim is `mongodb.persistence.existingClaim`
or there is none). Call with a dict of the root context (`root`) and the
Deployment (`resource`).
*/}}
{{- define "drs-filer.failIfLegacy" -}}
{{- $owner := dig "metadata" "annotations" "meta.helm.sh/release-name" "" .resource -}}
{{- $labels := dig "metadata" "labels" dict .resource -}}
{{- $name := dig "metadata" "name" "" .resource -}}
{{- if eq $owner .root.Release.Name -}}
{{- if not (hasKey $labels "app.kubernetes.io/instance") -}}
{{- fail (printf "release %s was installed with a chart before foca-common, and upgrading it would start the app on a new, empty database (Deployment %s): uninstall it and install the current chart instead, moving the data as described in deployment/README.md (From earlier charts)" .root.Release.Name $name) -}}
{{- end -}}
{{- $appName := include "foca-common.name" .root -}}
{{- if ne (get $labels "app.kubernetes.io/name") $appName -}}
{{- fail (printf "release %s was installed with the name label %s, and upgrading it with %s (a changed nameOverride) would change the selectors of its Services, but not those of its Deployments: keep nameOverride of the installation (see deployment/README.md, Names and labels)" .root.Release.Name (get $labels "app.kubernetes.io/name") $appName) -}}
{{- end -}}
{{- $mongodb := include "foca-common.mongodbFullname" .root -}}
{{- $persistence := .root.Values.mongodb.persistence | default dict -}}
{{- $generatedClaim := and $persistence.enabled (not $persistence.existingClaim) -}}
{{- if and .root.Values.mongodb.enabled $generatedClaim (eq (get $labels "app.kubernetes.io/component") "mongodb") (ne $name $mongodb) -}}
{{- fail (printf "release %s runs MongoDB as %s, and upgrading it with the name %s (a changed fullnameOverride or nameOverride) would start MongoDB on a new, empty claim: keep the names of the installation (see deployment/README.md, Names and labels)" .root.Release.Name $name $mongodb) -}}
{{- end -}}
{{- end -}}
{{- end -}}
