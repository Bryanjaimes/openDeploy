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

## Apply sample OpenDeploy resource

```bash
kubectl apply -f k8s/sample/opendeploy-sample.yaml
```

## Next steps

- Implement the operator controller (reconcile `OpenDeploy` -> Deployment/Service)
- Add Karpenter provisioner configs and KEDA ScaledObject