# DRS filer Helm chart

## Quick start

1. Edit `values.yaml`. It is important to change `host_name` to the URL you want the application to respond to.

2. Install the Helm chart. Run this from the `deployment` folder:
```
helm install drs-filer . -n namespace
```
`namespace` is the name of the namespace where the cluster should be installed.
`drs-filer` could be any name, it will be referenced later for upgrading or uninstalling.

## Upgrades

If you need to change any parameter of the deployment, the procedure is similar to installing:

1. Edit `values.yaml` with the new configuration you want to apply. For example, if you want to change the image of drs-filer, change `drs_filer.image`.

2. Upgrade the Helm chart. Run this from the `deployment` folder:
```
helm upgrade drs-filer . -n namespace
```
`namespace` is the name of the namespace where the cluster was installed.
`drs-filer` is the name given when installing. In order to see the correct name, do a `helm ls -n namespace`.

