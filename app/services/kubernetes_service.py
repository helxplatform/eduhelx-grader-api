import base64
import os
from kubernetes import client, config
from app.models.user import UserType

class KubernetesService:
    def __init__(self):
        self.api_instance = self.get_v1_client()

    @staticmethod
    def get_v1_client() -> client.CoreV1Api:
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()

        return client.CoreV1Api()
    
    def get_current_namespace(self):
        # This will exist if ran in-cluster with a service account
        ns_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
        if os.path.exists(ns_path):
            with open(ns_path, "r") as f:
                return f.read().strip()
        try:
            # Doesn't work when ran in-cluster (there is no kubeconfig)
            contexts, current_context = config.list_kube_config_contexts()
            return current_context["context"]["namespace"]
        except KeyError:
            return "default"

    def create_credential_secret(self, course_name: str, onyen: str, password: str, user_type: UserType):
        current_namespace = self.get_current_namespace()

        secret_name = self._compute_credential_secret_name(course_name, onyen)
        secret_data = {
            "onyen": onyen,
            "password": password,
            "class": course_name,
            "user_type": user_type.value,
        }
        encoded_secret_data = {
            key: base64.b64encode(value.encode()).decode() for (key, value) in secret_data.items()
        }

        secret = client.V1Secret(
            api_version="v1",
            kind="Secret",
            metadata=client.V1ObjectMeta(
                name=secret_name,
                namespace=current_namespace
            ),
            type="Opaque",
            data=encoded_secret_data
        )

        self.api_instance.create_namespaced_secret(
            namespace=current_namespace,
            body=secret
        )

    def delete_credential_secret(self, course_name: str, onyen: str):
        current_namespace = self.get_current_namespace()

        secret_name = self._compute_credential_secret_name(course_name, onyen)
        try:
            self.api_instance.delete_namespaced_secret(
                namespace=current_namespace,
                name=secret_name
            )
        except client.ApiException as e:
            # Don't error if the secret doesn't exist
            if e.status == 404:
                return
            raise e

    @staticmethod
    def _compute_credential_secret_name(course_name: str, onyen: str) -> str:
        # Secret names are subject to RFC 1123 meaning they cannot contain uppercase characters, spaces, or underscores.
        return f"{course_name.lower().replace(' ', '-')}-{onyen.lower()}-credential-secret"