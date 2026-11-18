# Helm chart

The chart deploys DRS-Filer on Kubernetes (and OpenShift): the app and a
MongoDB database. It is a thin chart over FOCA's library chart `foca-common`
(the version in `Chart.yaml`), which renders the resources from the values
described here and in `values.yaml` (see the [library chart's
documentation](https://github.com/elixir-cloud-aai/foca/blob/chart-v0.5.0/docs/helm-chart.md)).
The chart in the repository downloads the library chart with `helm
dependency build` (see [Installation](#installation)).

> **Warning:** DRS-Filer has no authentication: everyone who can reach the
> app can register, change and delete objects. Restrict who can reach it
> (see [Access](#access)).

## Configuration

The image contains the app's complete base config
([`drs_filer/config.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/drs_filer/config.yaml)).
The chart renders a config overlay into the `<app>-config` ConfigMap (see
[Names and labels](#names-and-labels)), which FOCA merges into the base
config on startup (via `FOCA_CONFIG_OVERLAY`):

- `custom.service` (`url_prefix`, `external_host` and `external_port`) is
  set to the public URL of the app, `https://<hostName>` on port 443, which the app
  puts into the `self_uri` of objects; `hostName` is **required** (rendering
  fails without it). Serve the app over HTTPS for it (see [Exposing the
  app](#exposing-the-app)).
- `db.host` is set to the release's MongoDB Service (`<app>-mongodb`),
  unless MongoDB is external (see [External MongoDB](#external-mongodb)).
- `config` overrides keys of the base config; it takes precedence over the
  generated values. Mappings are merged recursively, all other values
  (including lists) replace those of the base config (see
  [Configuration](https://drs-filer.readthedocs.io/en/latest/configuration/)).
  `server.host` and `server.port` have no effect, as they apply to the
  development server only (see [Server](#server)).

Keep the values of each deployment in its own values file outside this
repository (e.g., `values-prod.yaml` in the deployment's infrastructure
repository), for example:

```yaml
hostName: drs.example.org
drsFiler:
  tag: sha-0123456789abcdef0123456789abcdef01234567
mongodb:
  auth:
    existingSecret: drs-filer-mongodb-credentials
config:
  service_info:
    service:
      id: org.example.drs
      name: Example DRS
      description: Data objects of the Example Organization
      organization:
        name: Example Organization
        url: https://example.org
      contactUrl: mailto:drs-admins@example.org
      environment: prod
```

Without `service_info.service`, deployments serve the **placeholder
service info** of the base config (`id: org.example.drs-filer`, organization
`Example Organization`; see [Service
info](https://drs-filer.readthedocs.io/en/latest/configuration/#service-info));
its `version` is that of the image's app, unless set. The value
`config.endpoints` of earlier versions fails rendering, naming the keys
that replace it (see
[Upgrading](https://drs-filer.readthedocs.io/en/latest/upgrading/#typed-configuration)).
The app checks the config on startup and refuses to start, with the reason
in its log (check with `kubectl logs` and `kubectl rollout status` after
installs and upgrades). Pods are restarted when the ConfigMap changes.
Don't edit the ConfigMap with `kubectl edit`: Helm overwrites it on the next
upgrade. As `config` is stored in a ConfigMap, it must not contain secrets;
pass them as environment variables from Secrets (`drsFiler.extraEnv`,
`drsFiler.extraEnvFrom`, see [Server](#server)).

## Image

The app image is `drsFiler.image` (default `docker.io/elixircloud/drs-filer`)
with tag `drsFiler.tag`, which defaults to the chart's `appVersion`. In the
repository, `version` and `appVersion` are placeholders, and `appVersion` is
`dev`: the chart deploys the latest image of branch `dev`, which changes
with every commit. Deployments should set the tag of a commit on `dev`
(`sha-<commit>`, the full commit SHA) in the values file:

```yaml
drsFiler:
  tag: sha-0123456789abcdef0123456789abcdef01234567
```

`drsFiler.image` may also include a tag or digest (e.g.,
`docker.io/elixircloud/drs-filer:dev`, as in earlier charts); then
`drsFiler.tag` must be empty. Charts packaged for releases set the release
version as `version` and `appVersion`, so they deploy the image of their
release.

The image is pulled on every start of a pod (`drsFiler.imagePullPolicy:
Always`), so that moving tags such as `dev` deploy the latest image; set
`IfNotPresent` for fixed tags or digests, or `Never` for images loaded into
the nodes (e.g., with `kind load`).

## Installation

MongoDB requires authentication: create a Secret with its credentials in the
namespace first, and set its name in `mongodb.auth.existingSecret` (see
[Authentication](#authentication)); otherwise, rendering fails. E.g., with
random passwords:

```bash
kubectl create namespace <namespace>
kubectl create secret generic drs-filer-mongodb-credentials -n <namespace> \
    --from-literal=root-username=root \
    --from-literal=root-password="$(openssl rand -hex 24)" \
    --from-literal=username=drs-filer \
    --from-literal=password="$(openssl rand -hex 24)"
```

From the root of the repository, download the library chart (into
`deployment/charts/`, the version locked in `Chart.lock`) and install the
chart, with `drsFiler.tag` set in the values file (see [Image](#image)):

```bash
helm dependency build deployment
helm install drs-filer deployment -n <namespace> -f values-prod.yaml
```

`<namespace>` is the namespace to deploy to; `drs-filer` is the name of the
release, which is referenced when upgrading or uninstalling. Helm prints the
app's URL and a test request after installing (`helm get notes drs-filer -n
<namespace>` shows them again; `helm show values deployment` prints the
defaults).

## Names and labels

Resource names are derived from the release name, so that several releases
can be installed in one namespace:

- **App** (Deployment, Service, Ingress, HTTPRoute or Route, NetworkPolicy,
  PodDisruptionBudget; ConfigMap `<app>-config`): `<app>` is
  `<release>-drs-filer`, or the release name if it contains `drs-filer`
  (e.g., `drs-filer` for the release `drs-filer`, `prod-drs-filer` for the
  release `prod`);
- **MongoDB** (Deployment, Service, PersistentVolumeClaim, NetworkPolicy;
  ConfigMap `<app>-mongodb-init-script`): `<app>-mongodb`; the app connects
  to this Service.

`nameOverride` replaces `drs-filer` in the names and the
`app.kubernetes.io/name` label, `fullnameOverride` replaces `<app>`. Set them
when installing only: changing `nameOverride` later changes the pod
selectors of the Deployments, which can't be changed, and changing either
renames the resources, MongoDB's claim included, so MongoDB would start on a
new, empty claim (the old one is kept; unless the claim is
`mongodb.persistence.existingClaim`): `helm upgrade` fails then (when Helm
can query the cluster). Names are truncated to 63 characters. The examples
in this document use the release `drs-filer`.

All resources have the [standard
labels](https://helm.sh/docs/chart_best_practices/labels/)
(`app.kubernetes.io/name`, `instance`, `version` and `managed-by`, and
`helm.sh/chart`); pods are selected by name, instance and
`app.kubernetes.io/component` (`app` or `mongodb`), e.g.:

```bash
kubectl get pods -n <namespace> -l app.kubernetes.io/instance=drs-filer
```

## Exposing the app

The chart exposes the app for `hostName` in one of three ways (see
[Exposing the
app](https://github.com/elixir-cloud-aai/foca/blob/chart-v0.5.0/docs/helm-chart.md#exposing-the-app)
in the library chart's documentation for TLS, body size and rate limits,
NetworkPolicy peers and keep-alive settings of ingress-nginx, Traefik, the
Gateway API, OpenShift and cloud load balancers):

- an Ingress (`drsFiler.ingress`, enabled by default), for any ingress
  controller; `className` sets its class, `annotations` its annotations
  (e.g., for the ingress controller; they take precedence over those set by
  the chart for `https`, `null` removes one), and `https.enabled` requests a
  certificate from cert-manager (via the ClusterIssuer `https.issuer`);
- a Gateway API HTTPRoute (`drsFiler.httpRoute`), attached to an existing
  Gateway (`parentRefs`), optionally with a second HTTPRoute that redirects
  HTTP to HTTPS (`httpsRedirect`); set `drsFiler.ingress.enabled: false` to
  use it, e.g.:

    ```yaml
    drsFiler:
      ingress:
        enabled: false
      httpRoute:
        enabled: true
        parentRefs:
        - name: gateway
          namespace: gateway-system
          sectionName: https
        httpsRedirect:
          enabled: true
          parentRefs:
          - name: gateway
            namespace: gateway-system
            sectionName: http
    ```

- an OpenShift Route, with TLS termination at the router, which redirects
  HTTP to HTTPS, if neither is enabled, the cluster serves Routes
  (`route.openshift.io/v1`) and `drsFiler.route.enabled` is true (the
  default); otherwise the app is only reachable within the cluster, and Helm
  prints a warning after installing. On OpenShift (e.g., CSC's Rahti),
  disable the Ingress, which is enabled by default and has no TLS unless you
  configure it: the chart then creates the Route.

All of them route all paths (`/`) to the app. The app advertises
`https://<hostName>` URLs (the `self_uri` of objects), so serve it over
HTTPS only: by default, the Ingress has no TLS (`https.enabled: false`) and
serves plain HTTP, so TLS must be terminated in front of the cluster (e.g.,
by a load balancer); Helm's notes after installing say so.

By default, the app has no size limit of request bodies (set one in bytes
with `config.server.max_content_length`) and no rate limits, and the chart
sets none at the proxy: for production, limit both at the ingress controller
or Gateway (see the library chart's documentation, linked above;
ingress-nginx limits request bodies to 1 MiB by default).

### Forwarded headers

The ingress controller, Gateway or router terminates TLS and forwards
requests to the app via HTTP, with `X-Forwarded-*` headers. Gunicorn trusts
these headers from the local host only (its default), so URLs that the app
builds from the request get `http`; the `self_uri` of objects comes from
`hostName` (see [Configuration](#configuration)) and is not affected. To
keep `https` in such URLs, set the addresses that the ingress controller or
router connects from in Gunicorn's `FORWARDED_ALLOW_IPS`, via
`drsFiler.extraEnv`: addresses or networks in CIDR notation, comma-separated
(e.g., the nodes' subnet if the controller runs in the host network):

```yaml
drsFiler:
  extraEnv:
  - name: FORWARDED_ALLOW_IPS
    value: "192.0.2.0/24"
```

Every workload that can reach the app's pods from a trusted address can set
these headers. So never use `*` if clients can reach the app's pods
directly: a network trusts every address in it, and the pod network of the
cluster (e.g., `10.128.0.0/14` on OpenShift) contains every pod; restrict
who can reach the app's pods with its NetworkPolicy (see [Network
policies](#network-policies)). An invalid entry stops the app (Gunicorn
exits on startup).

## Access

DRS-Filer has no authentication and no access control: everyone who can
reach the API can read, register, change and delete objects, and change the
service info (`POST /service-info`; see [Access
control](https://drs-filer.readthedocs.io/en/latest/access-control/)). Helm's
notes after installing warn of it. Until the app has access control,
restrict access in front of it:

- expose the app on an internal network only, or not at all (disable the
  Ingress and, on OpenShift, the Route: `drsFiler.ingress.enabled: false`,
  `drsFiler.route.enabled: false`), and let only trusted clients in the
  cluster reach it, with the app's NetworkPolicy (see [Network
  policies](#network-policies));
- or allow the methods that change data (`POST`, `PUT`, `DELETE`) only from
  trusted clients, with the means of your ingress controller, Gateway or
  proxy. For example (an example only, adapt it to your setup), with
  ingress-nginx, which allows them only from the network `192.0.2.0/24`:

    ```yaml
    drsFiler:
      ingress:
        className: nginx
        annotations:
          nginx.ingress.kubernetes.io/configuration-snippet: |
            limit_except GET HEAD OPTIONS {
              allow 192.0.2.0/24;
              deny all;
            }
    ```

`allow` checks the source address that the controller sees, which is the
client's only if it gets through: behind a load balancer, e.g., with
`externalTrafficPolicy: Local` or the PROXY protocol. If the controller
trusts forwarded headers (`use-forwarded-headers`), limit them to your
proxies (`proxy-real-ip-cidr`), or anyone can claim an allowed address in
`X-Forwarded-For`. Recent versions of ingress-nginx disable snippet
annotations by default (the controller must allow them,
`allow-snippet-annotations`, and annotations of their risk level,
`annotations-risk-level: Critical`); a controller that doesn't allow them
ignores the annotation (or rejects the Ingress), leaving writes
unrestricted. ingress-nginx is also retired (no releases or security fixes
after March 2026). The OpenShift router can't restrict methods, only
clients, for all methods (e.g.,
`haproxy.router.openshift.io/ip_allowlist: 192.0.2.0/24` in
`drsFiler.route.annotations`). In every setup, check with a `POST` from an
untrusted address that writes are refused.

## Security context

All containers run as non-root users, without privilege escalation or
capabilities, with the runtime's default seccomp profile and a read-only
root file system, as the Pod Security Standard "restricted" requires; they
write to `emptyDir` volumes (`/tmp`) and MongoDB to its data volume. The app
image runs as user 1000; the MongoDB image uses user 999, which the chart
sets (`runAsUser`, `runAsGroup`), and `fsGroup` makes its data volume
writable (applied on a mismatch only, `fsGroupChangePolicy:
OnRootMismatch`). This needs storage that applies `fsGroup` (most
dynamically provisioned volumes do; e.g., `hostPath` and some CSI drivers
don't): otherwise, MongoDB can't write to a new volume and doesn't start. No
pod gets a service account token (`automountServiceAccountToken: false`), as
none calls the Kubernetes API.

The `/tmp` volumes are limited to 64 MiB each by `tmpSizeLimit` of
`drsFiler` and `mongodb` (a positive Kubernetes quantity, e.g., `64Mi`, or a
number of bytes; `null` removes the limit); the kubelet evicts pods that
exceed it.

On OpenShift (detected by the API `security.openshift.io/v1`), the chart
omits `runAsUser`, `runAsGroup` and `fsGroup`, as OpenShift assigns them
from the namespace's range. The contexts are set in the values
(`podSecurityContext` and `securityContext` of `drsFiler` and `mongodb`);
mappings are merged with the defaults, and `null` removes a default. Some
clusters set their own seccomp profile and reject pods that ask for one,
such as the chart's default (`seccompProfile: {type: RuntimeDefault}`); on
such clusters, remove it (`drsFiler.podSecurityContext.seccompProfile: null`
and `mongodb.podSecurityContext.seccompProfile: null`), and the pods run
with the profile that the cluster assigns.

## Network policies

The chart creates
[NetworkPolicies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
that restrict which pods may connect to its pods (ingress); connections from
the pods are not restricted. They only take effect if the cluster's network
plugin enforces NetworkPolicies (e.g., Calico or Cilium). NetworkPolicies
add up: a pod that several policies select accepts the connections that any
of them allows (e.g., a namespace-wide "allow" policy).

- **MongoDB** (`mongodb.networkPolicy.enabled`, default `true`): only the
  app's pods of the same release may connect. Disable it if you manage
  policies yourself, or if other workloads (e.g., backups) must connect.
- **App** (`drsFiler.networkPolicy.enabled`, default `false`): only the
  NetworkPolicy peers in `drsFiler.networkPolicy.ingressFrom` may connect.
  There are none by default, as they depend on the cluster: when enabling
  the policy, set them to the pods of the cluster's ingress controller,
  Gateway or OpenShift router (see [NetworkPolicy
  peers](https://github.com/elixir-cloud-aai/foca/blob/chart-v0.5.0/docs/helm-chart.md#networkpolicy-peers)
  in the library chart's documentation), and add other clients in the
  cluster that call the app's Service directly; otherwise, the app is
  unreachable through the Ingress (or Route). Rendering fails if the policy
  is enabled without peers (which would allow all sources), e.g.:

    ```yaml
    drsFiler:
      networkPolicy:
        enabled: true
        ingressFrom:
        # ingress-nginx: its pods in the namespace `ingress-nginx`
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
          podSelector:
            matchLabels:
              app.kubernetes.io/name: ingress-nginx
    ```

    The policy also keeps other workloads from setting the forwarded
    headers that the app trusts (see [Forwarded
    headers](#forwarded-headers)) and, as the app has no authentication,
    from writing to it directly (see [Access](#access)).

`kubectl exec` and `kubectl port-forward` don't go through the pod network
and are not affected. The policies don't block the probes: connections from
the pod's own node, where the kubelet runs them, are allowed.

## Server

The image serves the app with Gunicorn on port 8080. The chart passes the
settings in `drsFiler.gunicorn` to it (via `GUNICORN_CMD_ARGS`); the
defaults are the image's (`drs_filer/gunicorn_config.py`: one worker process
with 4 threads, a timeout of 30 seconds, a graceful timeout of 20 seconds,
and a keep-alive of 100 seconds, longer than the upstream keep-alive timeout
of common ingress controllers: 60 seconds for ingress-nginx, 90 seconds for
Traefik). Rendering fails if `extraArgs` set `--bind`/`-b`, `--preload` or
`--graceful-timeout`. On shutdown, the app keeps serving for
`drsFiler.preStopSleepSeconds` (default 5) before Gunicorn stops, so that
the ingress controller stops sending requests to the pod first.

`drsFiler.extraEnv` (Kubernetes `EnvVar`s) and `drsFiler.extraEnvFrom`
(`EnvFromSource`s) add environment variables to the app's container, e.g.,
`FORWARDED_ALLOW_IPS` (see [Forwarded headers](#forwarded-headers)) or
settings from a Secret of your own; rendering fails for the variables that
the chart sets itself, and for secrets as literal values. Helm doesn't
restart the pods when a Secret changes, unless it is listed in
`drsFiler.rolloutOnSecrets` (which needs Helm to read the cluster, so not
with `helm template` or Argo CD); otherwise, restart them after changing one
(`kubectl rollout restart deploy/drs-filer -n <namespace>`).

`drsFiler.resources` sets the CPU and memory of the app: by default a
request of 256Mi and a limit of 384Mi memory, as for the other FOCA apps.
Each further Gunicorn worker loads the whole app, so add about 150Mi per
worker to the request and the limit before raising `workers`.
`mongodb.resources` sets those of MongoDB (by default 512Mi).

## Several replicas

`drsFiler.replicas` (default: 1) sets the number of the app's pods. With
more than one, the chart renders a PodDisruptionBudget, so that voluntary
disruptions (e.g., node drains) evict at most one pod at once; set
`drsFiler.podDisruptionBudget.minAvailable` or `maxUnavailable` to change
that, or `enabled: false` to render none. Objects are kept in MongoDB, so
the pods share them. See [Several
replicas](https://github.com/elixir-cloud-aai/foca/blob/chart-v0.5.0/docs/helm-chart.md#several-replicas)
in FOCA's docs for the caveats. The chart has no autoscaler.

## Probes

- **App:** ready once it serves its Swagger UI (`/ga4gh/drs/v1/ui/`, which
  doesn't need the database; set `drsFiler.probePath` if the config
  disables the Swagger UI); up to 5 minutes are allowed for the start.
  `drsFiler.startupProbe`, `drsFiler.readinessProbe` and
  `drsFiler.livenessProbe` (Kubernetes probe specs) each replace a default
  entirely.
- **MongoDB:** ready once it accepts connections.

## MongoDB

### Version

The chart pins MongoDB (`mongodb.image`, default `mongo:7.0`, the version
that CI tests; MongoDB 8.0 refuses to start on Linux kernels 6.19 to 7.0.13,
cf. [SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912)). Before
moving to 8.0, check the kernels of the nodes that MongoDB may run on (nodes
added later, e.g., by an autoscaler, must have compatible kernels too):

```bash
kubectl get nodes -o custom-columns=NODE:.metadata.name,KERNEL:.status.nodeInfo.kernelVersion
```

MongoDB only starts on data whose feature compatibility version (FCV) it
supports, so check the running version and the FCV before changing the
image of an existing database:

```bash
kubectl exec deploy/drs-filer-mongodb -n <namespace> -- sh -c \
  'mongosh --quiet \
  -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --eval "printjson({version: db.version(), fcv: db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion})"'
```

(Without authentication, leave out `-u`, `-p` and
`--authenticationDatabase`; the same holds for the other `mongosh`,
`mongodump` and `mongorestore` commands of this page.)

- **Upgrades** go one major version at a time (e.g., 6.0 → 7.0 → 8.0): set
  the image of the next version, wait for the rollout, then set the FCV to
  that version (e.g.,
  `db.adminCommand({setFeatureCompatibilityVersion: "8.0", confirm: true})`)
  before the next step.
- **Downgrades** are not supported by the `mongo` images (MongoDB Community
  Edition): keep the running major and minor version (as `db.version()`
  reports it, e.g., `mongodb.image: docker.io/library/mongo:8.2`), or dump
  the database (`mongodump`) and restore it (`mongorestore`) into a new,
  empty volume with the older version.

The MongoDB Deployment uses the `Recreate` strategy, as the data volume can
only be used by one pod: changing the image stops MongoDB, and an image that
can't read the data leaves it down until the image is changed back.

### Authentication

MongoDB requires credentials (`mongodb.auth.enabled`, by default `true`).
They come from an existing Secret in the release's namespace, named by
`mongodb.auth.existingSecret`, with four keys (see
[Installation](#installation)):

- `root-username` and `root-password`: MongoDB's root user (in the database
  `admin`), for administration (e.g., the commands in [Version](#version));
- `username` and `password`: the app user, with the role `readWrite` on the
  app's database, `drsStore`, only, in which it is created; the app
  connects as this user (FOCA's `MONGO_USERNAME` and `MONGO_PASSWORD`).

Without a Secret name, rendering fails. To run MongoDB without
authentication, set `mongodb.auth.enabled: false` explicitly; any pod that
can reach the MongoDB Service can then read and change the data (Helm's
notes after installing warn of it). Credentials never appear in values
files or ConfigMaps.

MongoDB creates both users when it starts with an empty volume (the root
user by its image's entrypoint, the app user by the init script of the
ConfigMap `<app>-mongodb-init-script`), and enforces authentication on every
start. Changing the Secret doesn't change the users: to change a password,
change it in MongoDB first (e.g.,
`db.getSiblingDB("drsStore").changeUserPassword("drs-filer", "<new
password>")` as the root user), then update the Secret and restart the app
(`kubectl rollout restart deploy/drs-filer -n <namespace>`); its requests to
the database fail until then. After changing the root user's password, also
restart MongoDB (`kubectl rollout restart deploy/drs-filer-mongodb -n
<namespace>`), whose environment the commands in this README use for the
root user's credentials. See [Deployment
notes](https://github.com/elixir-cloud-aai/foca/blob/chart-v0.5.0/docs/helm-chart.md#deployment-notes)
of the library chart for creating the users of an existing database.

### Persistence

MongoDB keeps its data in a PersistentVolumeClaim (`<app>-mongodb`;
`mongodb.persistence`: `size`, by default `1Gi`, `accessModes`,
`storageClass`, or an `existingClaim`). Helm keeps the claim, and with it
the database, when the release is uninstalled
(`mongodb.persistence.resourcePolicy: keep`); a new release of the same name
in the same namespace uses it again. To remove the data, delete the claim
after uninstalling the release (`kubectl delete pvc drs-filer-mongodb -n
<namespace>`; with the reclaim policy `Retain`, also delete its
PersistentVolume and the storage behind it with your storage provider).
With `mongodb.persistence.enabled: false` (e.g., for tests), the data is
lost when MongoDB's pod is replaced.

### External MongoDB

To use a MongoDB outside the release (e.g., a managed database), set
`mongodb.enabled: false` and its host (and port) in the config; rendering
fails without `config.db.host`:

```yaml
mongodb:
  enabled: false
  auth:
    # Secret with the keys `username` and `password` of the app user
    existingSecret: drs-filer-mongodb-credentials
config:
  db:
    host: mongodb.example.org
    port: 27017
```

The app authenticates as the app user against its database (`drsStore`), so
create that user there, with the `readWrite` role on `drsStore`, which
includes the right to create the indexes that the app creates on startup;
allow the app's pods to connect to the database. Give each release a
database server of its own: releases that share one use the same database,
and so serve and change each other's objects.

## Upgrades

Change the values file (e.g., `config` for the config, `drsFiler.tag` for
the image) and upgrade the release, from the root of the repository:

```bash
helm dependency build deployment
helm upgrade drs-filer deployment -n <namespace> -f values-prod.yaml
```

Upgrade with the values file (`-f`), not with `--reuse-values`, which would
keep values that the chart no longer has, and without the defaults of the
new chart. The app's pods are replaced when the config changes. See
[Upgrading](https://drs-filer.readthedocs.io/en/latest/upgrading/) for the
changes of the app since the last deployed version.

### From earlier charts

The charts before the library chart (version 3.0.0 and earlier) used other
values, resource names and selectors, ran MongoDB without authentication
and with the unpinned image `mongo:noble` (the latest MongoDB release), and
didn't keep MongoDB's claim (`mongodb`) on uninstall. The current chart
renames the resources (see [Names and labels](#names-and-labels); e.g.,
`mongodb` becomes `drs-filer-mongodb`) and changes the selectors of the
Deployments, which can't be changed in place, so **releases of earlier
charts can't be upgraded: uninstall them and install the current chart,
moving the data.** `helm upgrade` fails for releases with Deployments of an
earlier chart (only when Helm can query the cluster: not in `helm template`
or client-side dry runs).

Rendering fails for the values of earlier charts, which the current chart
would ignore:

| Earlier values | Now |
| --- | --- |
| `host_name` | `hostName` |
| `drs_filer.ingress` (`true` or `false`) | `drsFiler.ingress.enabled` (with `false`, an OpenShift Route, see [Exposing the app](#exposing-the-app)) |
| `drs_filer.image` (with the tag, e.g., `elixircloud/drs-filer:dev`) | `drsFiler.image` and `drsFiler.tag` (or the image with the tag and an empty `drsFiler.tag`, see [Image](#image)) |
| `drs_filer.appName` (default `drs-filer`, the name of the ConfigMap) | `fullnameOverride`, the names of all resources (see [Names and labels](#names-and-labels)) |
| `drs_filer.resources` | `drsFiler.resources` |
| `apiServer` (charts with the config Job) | none: the chart renders the config overlay itself |
| `clusterType` | none: a Route is created on OpenShift without an Ingress or HTTPRoute (see [Exposing the app](#exposing-the-app)) |
| `mongodb.volumeSize` | `mongodb.persistence.size` |

`mongodb.image` keeps its name; set it to an image pinned to a minor
version (see [Version](#version)) instead of `mongo:noble`.

**Uninstalling a release of an earlier chart deletes MongoDB's claim
`mongodb`, and with it the data** (unless its PersistentVolume has the
reclaim policy `Retain`): dump the database first. The database keeps its
name, `drsStore`. The app is down from the first to the last step. The
earlier charts always named the Deployments `drs-filer` and `mongodb` and
labelled the app's pods `app: drs-filer`, whatever `drs_filer.appName` was
(it named the ConfigMap only); the commands are for the release
`drs-filer`:

1. Stop the app and wait until its pods are gone, so that the data doesn't
   change during the dump:

    ```bash
    kubectl scale deploy/drs-filer -n <namespace> --replicas=0
    kubectl wait pod -l app=drs-filer -n <namespace> --for=delete --timeout=120s
    ```

2. Dump the app's database to a local file (the earlier MongoDB has no
   authentication), and check that MongoDB can read the dump; continue only
   if `Dump OK` is printed:

    ```bash
    kubectl exec deploy/mongodb -n <namespace> -- \
      mongodump --quiet --db drsStore --archive > drsStore.archive \
    && kubectl exec -i deploy/mongodb -n <namespace> -- \
      mongorestore --dryRun --archive < drsStore.archive \
    && echo "Dump OK"
    ```

3. Note the MongoDB version of the earlier release (`kubectl exec
   deploy/mongodb -n <namespace> -- mongod --version`), uninstall the
   release (`helm uninstall drs-filer -n <namespace>`), and update the
   values file (see the table above). The dump is a logical one, so the new
   release's MongoDB (`mongo:7.0` by default) restores it, also if the
   earlier one ran a later version. Create the Secret with MongoDB's
   credentials (see [Installation](#installation)).

4. Install the current chart (see [Installation](#installation)), stop its
   app again and wait until its pods are gone, so that it doesn't write
   during the restore, and wait for MongoDB:

    ```bash
    kubectl scale deploy/drs-filer -n <namespace> --replicas=0
    kubectl wait pod -n <namespace> --for=delete --timeout=120s \
      -l app.kubernetes.io/instance=drs-filer,app.kubernetes.io/component=app
    kubectl rollout status deploy/drs-filer-mongodb -n <namespace>
    ```

5. Restore the dump, replacing the collections that the app has created,
   and start the app only if the restore succeeded (`Restore OK`);
   otherwise, the app stays stopped, and the restore can be repeated
   (`--drop`). The command starts one pod: with more `drsFiler.replicas`,
   set that number in `--replicas`:

    ```bash
    kubectl exec -i deploy/drs-filer-mongodb -n <namespace> -- sh -c \
      'mongorestore --quiet --drop --archive \
      -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
      --authenticationDatabase admin' < drsStore.archive \
    && echo "Restore OK" \
    && kubectl scale deploy/drs-filer -n <namespace> --replicas=1
    ```

6. Check that the app serves the objects (e.g., `curl -s
   'https://drs.example.org/ga4gh/drs/v1/objects/<id>'` for an object
   registered before), then delete the dump.
