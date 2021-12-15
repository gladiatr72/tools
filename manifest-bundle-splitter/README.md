
# (kubernetes) manifest-bundle-splitter

The utility exists to split a bundled (YAML) kubernetes manifest
into its component documents, writing said documents to individual
files within the specified directory ($PWD by default)

The component document files are prefixed with an integer denoting
its _kind_.  This prefix is set on a _first-seen_ basis. Because of
how Kubernetes and its adjacent projects work, the more important
object _kinds_ end up at the top of the manifest stack during
installation.

Using this as a hint-source, object docs that are most likely to be
depended-on by other objects will percolate to the top of the pile.


example:

	```
		kind: Namespace
		kind: CustomResourceDefinition
		kind: CustomResourceDefinition
		...
		kind: ServiceAccount
		kind: ServiceAccount
		...
		kind: ClusterRole
		kind: ClusterRoleBinding
		kind: ClusterRoleBinding
		kind: Service
		kind: Service
		kind: Service
		kind: Deployment
		kind: Deployment
		...
		kind: NetworkPolicy
		kind: NetworkPolicy
	```


will produce files with the following prefix pattern:

	```
		00--Namespace--A
		00--Namespace--B
		01--CustomResourceDefinition--A
		01--CustomResourceDefinition--B
		etc...
	```


---

This covers the cases such as the output from `helm template` as well as the
delightful alternatives-to-helm such as the output from `flux install --dry-run --verbose`

---


## Rationale

Flux is pretty cool once it is configured.  Unfortunately, the aforementioned output
of `flux install` is a giant YAML bundle.  On the _very real chance_ that it will be necessary
to tune this installation, the _documented_ solution is to use !flux/kustomization documents
that are destined to be resolved by Flux's _kustomization-controller_.

Or the giant bundle can be replaced with its components.  Need to change the log level for
a particular flux component?  Go to that component's manifest in the _flux-fleet_ repository
and either make the update directly or create a specific kustomization that matches the
parent object properly.


## Usage

`manifest-bundle-splitter --verbose (-v) --output_path (-o) --bundle (-i)`

The default output path is ```.`.

	```

		manifest-bundle-splitter -v -o /tmp/flux-manifests -i ~/git/flux-fleet/flux-system/gotk-components.yaml

		writing Namespace/flux-system.yaml to /tmp/flux-manifests/00--Namespace--flux-system.yaml
		writing CustomResourceDefinition/alerts.notification.toolkit.fluxcd.io.yaml to /tmp/flux-manifests/01--CustomResourceDefinition--alerts.notification.toolkit.fluxcd.io.yaml
		writing CustomResourceDefinition/buckets.source.toolkit.fluxcd.io.yaml to /tmp/flux-manifests/01--CustomResourceDefinition--buckets.source.toolkit.fluxcd.io.yaml
		writing CustomResourceDefinition/gitrepositories.source.toolkit.fluxcd.io.yaml to /tmp/flux-manifests/01--CustomResourceDefinition--gitrepositories.source.toolkit.fluxcd.io.yaml
		writing CustomResourceDefinition/helmcharts.source.toolkit.fluxcd.io.yaml to /tmp/flux-manifests/01--CustomResourceDefinition--helmcharts.source.toolkit.fluxcd.io.yaml
		writing CustomResourceDefinition/helmreleases.helm.toolkit.fluxcd.io.yaml to /tmp/flux-manifests/01--CustomResourceDefinition--helmreleases.helm.toolkit.fluxcd.io.yaml
		writing CustomResourceDefinition/helmrepositories.source.toolkit.fluxcd.io.yaml to /tmp/flux-manifests/01--CustomResourceDefinition--helmrepositories.source.toolkit.fluxcd.io.yaml
		writing CustomResourceDefinition/imagepolicies.image.toolkit.fluxcd.io.yaml to /tmp/flux-manifests/01--CustomResourceDefinition--imagepolicies.image.toolkit.fluxcd.io.yaml
		writing CustomResourceDefinition/imagerepositories.image.toolkit.fluxcd.io.yaml to /tmp/flux-manifests/01--CustomResourceDefinit
		[...]

	```

or

	```
		flux install --verbose --dry-run | manifest-bundle-splitter -v -o /tmp/flux-manifests
		[...]
	```


