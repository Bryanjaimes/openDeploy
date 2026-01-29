import os
import time
import logging
from typing import Dict, Any, List

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

GROUP = "opendeploy.dev"
VERSION = "v1alpha1"
PLURAL = "opendeploys"


def load_kube_config():
    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()


def get_namespace(obj: Dict[str, Any]) -> str:
    return obj.get("metadata", {}).get("namespace", "default")


def build_env(env_list: List[Dict[str, str]]) -> List[client.V1EnvVar]:
    return [client.V1EnvVar(name=item.get("name"), value=item.get("value")) for item in env_list]


def build_resources(spec: Dict[str, Any]) -> client.V1ResourceRequirements:
    resources = spec.get("resources", {})
    limits = {}
    requests = {}

    if resources.get("cpu"):
        limits["cpu"] = resources["cpu"]
        requests["cpu"] = resources["cpu"]
    if resources.get("memory"):
        limits["memory"] = resources["memory"]
        requests["memory"] = resources["memory"]
    if resources.get("gpu"):
        limits["nvidia.com/gpu"] = resources["gpu"]
        requests["nvidia.com/gpu"] = resources["gpu"]

    return client.V1ResourceRequirements(limits=limits or None, requests=requests or None)


def ensure_deployment(apps_v1: client.AppsV1Api, obj: Dict[str, Any]):
    metadata = obj.get("metadata", {})
    spec = obj.get("spec", {})
    name = metadata.get("name")
    namespace = get_namespace(obj)

    image = spec.get("image")
    replicas = spec.get("replicas", 1)
    port = spec.get("port", 8000)
    env = build_env(spec.get("env", []))
    resources = build_resources(spec)

    labels = {
        "app": "opendeploy",
        "opendeploy/name": name,
    }

    deployment = client.V1Deployment(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
        spec=client.V1DeploymentSpec(
            replicas=replicas,
            selector=client.V1LabelSelector(match_labels=labels),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name="api",
                            image=image,
                            ports=[client.V1ContainerPort(container_port=port)],
                            env=env,
                            resources=resources,
                        )
                    ]
                ),
            ),
        ),
    )

    try:
        apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
        apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=deployment)
        logging.info("Patched Deployment %s/%s", namespace, name)
    except ApiException as e:
        if e.status == 404:
            apps_v1.create_namespaced_deployment(namespace=namespace, body=deployment)
            logging.info("Created Deployment %s/%s", namespace, name)
        else:
            raise


def ensure_service(core_v1: client.CoreV1Api, obj: Dict[str, Any]):
    metadata = obj.get("metadata", {})
    spec = obj.get("spec", {})
    name = metadata.get("name")
    namespace = get_namespace(obj)
    port = spec.get("port", 8000)

    labels = {
        "app": "opendeploy",
        "opendeploy/name": name,
    }

    service = client.V1Service(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
        spec=client.V1ServiceSpec(
            selector=labels,
            ports=[client.V1ServicePort(port=port, target_port=port)],
            type="ClusterIP",
        ),
    )

    try:
        core_v1.read_namespaced_service(name=name, namespace=namespace)
        core_v1.patch_namespaced_service(name=name, namespace=namespace, body=service)
        logging.info("Patched Service %s/%s", namespace, name)
    except ApiException as e:
        if e.status == 404:
            core_v1.create_namespaced_service(namespace=namespace, body=service)
            logging.info("Created Service %s/%s", namespace, name)
        else:
            raise


def delete_resources(apps_v1: client.AppsV1Api, core_v1: client.CoreV1Api, obj: Dict[str, Any]):
    name = obj.get("metadata", {}).get("name")
    namespace = get_namespace(obj)
    try:
        apps_v1.delete_namespaced_deployment(name=name, namespace=namespace)
        logging.info("Deleted Deployment %s/%s", namespace, name)
    except ApiException as e:
        if e.status != 404:
            raise

    try:
        core_v1.delete_namespaced_service(name=name, namespace=namespace)
        logging.info("Deleted Service %s/%s", namespace, name)
    except ApiException as e:
        if e.status != 404:
            raise


def update_status(custom_api: client.CustomObjectsApi, apps_v1: client.AppsV1Api, core_v1: client.CoreV1Api, obj: Dict[str, Any]):
    name = obj.get("metadata", {}).get("name")
    namespace = get_namespace(obj)

    try:
        deployment = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
        ready_replicas = deployment.status.ready_replicas or 0
    except ApiException:
        ready_replicas = 0

    endpoint = f"http://{name}.{namespace}.svc.cluster.local"

    status_body = {
        "status": {
            "readyReplicas": ready_replicas,
            "endpoint": endpoint
        }
    }

    try:
        custom_api.patch_namespaced_custom_object_status(
            GROUP,
            VERSION,
            namespace,
            PLURAL,
            name,
            status_body,
        )
    except ApiException as e:
        logging.error("Failed to update status for %s/%s: %s", namespace, name, e)


def reconcile(apps_v1: client.AppsV1Api, core_v1: client.CoreV1Api, custom_api: client.CustomObjectsApi, obj: Dict[str, Any]):
    ensure_deployment(apps_v1, obj)
    ensure_service(core_v1, obj)
    update_status(custom_api, apps_v1, core_v1, obj)


def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    load_kube_config()

    apps_v1 = client.AppsV1Api()
    core_v1 = client.CoreV1Api()
    custom_api = client.CustomObjectsApi()

    namespace = os.getenv("WATCH_NAMESPACE", "")
    logging.info("Watching OpenDeploy resources in namespace: %s", namespace or "all")

    w = watch.Watch()
    while True:
        try:
            stream = custom_api.list_cluster_custom_object if not namespace else custom_api.list_namespaced_custom_object
            stream_args = [GROUP, VERSION, PLURAL] if not namespace else [GROUP, VERSION, namespace, PLURAL]

            for event in w.stream(stream, *stream_args):
                obj = event.get("object")
                event_type = event.get("type")
                if not obj:
                    continue

                if event_type in {"ADDED", "MODIFIED"}:
                    reconcile(apps_v1, core_v1, custom_api, obj)
                elif event_type == "DELETED":
                    delete_resources(apps_v1, core_v1, obj)
        except Exception as exc:
            logging.error("Watcher error: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()