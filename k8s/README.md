# OpenDeploy K8s Operator (Scaffold)

This is the initial Kubernetes scaffolding for V3 (Elastic Cluster). It includes:

- CRD for `OpenDeploy` resources
- RBAC for the operator
- Placeholder operator deployment
- Sample `OpenDeploy` resource

## Apply CRD + RBAC

```bash
kubectl apply -f k8s/crd/opendeploy.yaml
kubectl apply -f k8s/rbac.yaml
```

## Apply operator deployment

```bash
kubectl apply -f k8s/operator-deployment.yaml
```

## Build operator image

```bash
docker build -t ghcr.io/bryanjaimes/opendeploy-operator:dev -f operator/Dockerfile .
docker push ghcr.io/bryanjaimes/opendeploy-operator:dev
```

## Apply sample OpenDeploy resource

```bash
kubectl apply -f k8s/sample/opendeploy-sample.yaml
```

## Autoscaling (HPA via operator)

The operator now creates an HPA when `spec.autoscaling` is present in an `OpenDeploy` resource.

```yaml
autoscaling:
	minReplicas: 1
	maxReplicas: 3
	cpuUtilization: 70
```

## KEDA (scale-to-zero)

Requires KEDA installed in the cluster.

```bash
kubectl apply -f k8s/keda/opendeploy-demo-scaledobject.yaml
```

## Karpenter (node provisioning)

Requires Karpenter installed and a discovery tag on subnets/security groups.

```bash
kubectl apply -f k8s/karpenter/opendeploy-ec2nodeclass.yaml
kubectl apply -f k8s/karpenter/opendeploy-nodepool.yaml
```

## Next steps

- Wire KEDA triggers to request rate (HTTP/RPS)
- Add Prometheus metrics adapter for autoscaling signals