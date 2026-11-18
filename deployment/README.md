# DRS-Filer Helm chart

Helm chart for deploying [DRS-Filer](https://github.com/elixir-cloud-aai/drs-filer)
on Kubernetes or OpenShift: the app, MongoDB with a persistent volume, their
Services, and an Ingress or an OpenShift Route.

The [deployment guide](https://drs-filer.readthedocs.io/en/latest/deployment/)
describes the values, how to install and upgrade the chart, and what changed
in chart 3.0.0; [Upgrading](https://drs-filer.readthedocs.io/en/latest/upgrading/)
lists the changes that need action. In short, from this directory, after
setting at least `host_name` in `values.yaml`:

```bash
helm install drs-filer . -n <namespace>
helm upgrade drs-filer . -n <namespace>
```
