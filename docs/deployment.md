# Deployment

DRS-Filer comes with a [Helm](https://helm.sh/) chart for Kubernetes and
OpenShift, in
[`deployment/`](https://github.com/elixir-cloud-aai/drs-filer/tree/dev/deployment)
(chart version 3.0.0): it deploys the app, MongoDB with a persistent volume,
their Services, and an Ingress (Kubernetes) or a Route (OpenShift).

!!! note "Being updated"
    The chart is being moved to the FOCA library chart
    ([#86](https://github.com/elixir-cloud-aai/drs-filer/issues/86)); this
    page will then describe the deployment in full. Until then, check the
    chart's
    [`values.yaml`](https://github.com/elixir-cloud-aai/drs-filer/blob/dev/deployment/values.yaml)
    against the [upgrade notes](upgrading.md).

!!! warning "No authentication yet"
    The chart exposes the API without authentication (see [Access
    control](access-control.md)); restrict access to it in front of the app.

## Installing

1. Set the values in `values.yaml`, at least `host_name`, the host name
   that the app is served at. The chart writes it, with the MongoDB host, to
   a config overlay in the ConfigMap `<appName>-config`, which the app merges
   into its config on startup (`FOCA_CONFIG_OVERLAY`, see
   [Configuration](configuration.md#overlays)).

    | Value | Default | Description |
    | --- | --- | --- |
    | `host_name` | `""` | Public host name of the app (Ingress or Route, and the `self_uri` of objects) |
    | `drs_filer.ingress` | `true` | `true`: an Ingress (Kubernetes); `false`: an OpenShift Route |
    | `drs_filer.image` | `elixircloud/drs-filer:dev` | Image of the app |
    | `drs_filer.appName` | `drs-filer` | Name of the app's resources |
    | `drs_filer.resources` | 100m CPU, 128Mi | Resources of the app |
    | `mongodb.image` | `docker.io/library/mongo:noble` | Image of MongoDB |
    | `mongodb.volumeSize` | `1Gi` | Size of MongoDB's persistent volume |
    | `mongodb.resources` | 200m CPU, 512Mi | Resources of MongoDB |

2. Install the chart, from the `deployment` directory, into the namespace
   `<namespace>`, as the release `drs-filer` (any name, used later to
   upgrade or uninstall it):

    ```bash
    helm install drs-filer . -n <namespace>
    ```

The chart doesn't set the service info: the app serves the placeholders of
the base config until a client sets it with `POST /service-info` (see
[Service info](configuration.md#service-info)).

## Upgrading

To change the deployment, edit `values.yaml` (e.g., `drs_filer.image` for
another image) and upgrade the release (`helm ls -n <namespace>` lists the
releases):

```bash
helm upgrade drs-filer . -n <namespace>
```

See [Upgrading](upgrading.md) for changes that need action.

### Upgrading to chart 3.0.0

Chart 3.0.0 replaces the Job that wrote the app's config into the ConfigMap
`app-config` (with a service account bound to the `admin` cluster role) by
the ConfigMap `<appName>-config`, which holds a config overlay; it needs an
image with `FOCA_CONFIG_OVERLAY` support (see
[Upgrading](upgrading.md#before-the-foca-022-upgrade)). The value
`apiServer` is gone. `helm upgrade` removes the Job, the service account, its
role binding and the old ConfigMap, as they are no longer part of the chart.

For local development and testing, use Docker Compose instead (see [Getting
started](getting-started.md)).
