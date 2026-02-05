# loadbalancer-k8s-operator

Charmhub: https://charmhub.io/loadbalancer-k8s

This charm creates (and keeps in sync) a Kubernetes `Service` of type `LoadBalancer`.
It does not run any application workload; instead, it points the Service selector at
pods that already exist in the cluster.

The created Service is named `<app>-lb` in the Juju model namespace.

## Usage

Deploy:

Deploy one charm per service, don't deploy multiple units.

```bash
juju deploy loadbalancer-k8s my-service-loadbalancer --resource image=registry.k8s.io/pause:3.9 --trust
```

Example deploy to expose `minio` on port 80:

```bash
juju deploy minio
juju deploy loadbalancer-k8s minio-loadbalancer --resource image=registry.k8s.io/pause:3.9 --config selector="app.kubernetes.io/name=minio" --config target-port=9000 --config lb-port=80 --trust
```

Configure it to point at your own pods:

```bash
juju config loadbalancer-k8s selector="app=myapp" target-port=8080 lb-port=80
```

Selector can also be provided as JSON:

```bash
juju config loadbalancer-k8s selector='{"app":"myapp","tier":"backend"}'
```

## Configuration

- `selector` (string): label selector for the backend pods.
	- Formats: `key=value,key2=value2` or a JSON object string.
- `target-port` (int): port on the selected pods.
- `lb-port` (int): port exposed by the LoadBalancer.
- `loadbalancer-annotations` (string): optional annotations applied to the Service.
	- Format: `key1=value1,key2=value2`
- `fixed-ip` (string): optional fixed IPv4/IPv6 address assigned to the Service.
	- Maps to Kubernetes Service `.spec.loadBalancerIP`.

Example annotations (cloud/provider specific):

```bash
juju config loadbalancer-k8s \
	loadbalancer-annotations="service.beta.kubernetes.io/aws-load-balancer-type=nlb"

Example fixed IP:

```bash
juju config loadbalancer-k8s fixed-ip=192.0.2.10
```
```

## Notes

- The charm is leader-gated: only the leader unit reconciles the Kubernetes Service.
- The charm does not create Deployments/Pods; ensure your backend pods exist and match the selector.
- If you change `selector`, `target-port`, `lb-port`, or `loadbalancer-annotations`, the Service is updated.
