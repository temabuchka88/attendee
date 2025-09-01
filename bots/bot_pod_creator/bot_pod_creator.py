import os
import uuid
from typing import Dict, Optional

from kubernetes import client, config

# fmt: off

class BotPodCreator:
    def __init__(self, namespace: str = "attendee"):
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        
        self.v1 = client.CoreV1Api()
        self.namespace = namespace
        
        # Get configuration from environment variables
        self.app_name = os.getenv('CUBER_APP_NAME', 'attendee')
        self.app_version = os.getenv('CUBER_RELEASE_VERSION')
        
        if not self.app_version:
            raise ValueError("CUBER_RELEASE_VERSION environment variable is required")
            
        # Parse instance from version (matches your pattern of {hash}-{timestamp})
        self.app_instance = f"{self.app_name}-{self.app_version.split('-')[-1]}"
        default_pod_image = f"nduncan{self.app_name}/{self.app_name}"
        self.image = f"{os.getenv('BOT_POD_IMAGE', default_pod_image)}:{self.app_version}"

    def create_bot_pod(
        self,
        bot_id: int,
        bot_name: Optional[str] = None,
        bot_cpu_request: Optional[int] = None,
        add_webpage_streamer: Optional[bool] = False,
    ) -> Dict:
        """
        Create a bot pod with configuration from environment.
        
        Args:
            bot_id: Integer ID of the bot to run
            bot_name: Optional name for the bot (will generate if not provided)
        """
        if bot_name is None:
            bot_name = f"bot-{bot_id}-{uuid.uuid4().hex[:8]}"

        if bot_cpu_request is None:
            bot_cpu_request = os.getenv("BOT_CPU_REQUEST", "4")

        # Set the command based on bot_id
        # Run entrypoint script first, then the bot command
        command = ["python", "manage.py", "run_bot", "--botid", str(bot_id)]

        # Metadata labels matching the deployment
        labels = {
            "app.kubernetes.io/name": self.app_name,
            "app.kubernetes.io/instance": self.app_instance,
            "app.kubernetes.io/version": self.app_version,
            "app.kubernetes.io/managed-by": "cuber",
            "app": "bot-proc"
        }

        annotations = {}
        if os.getenv("USING_KARPENTER", "false").lower() == "true":
            annotations["karpenter.sh/do-not-disrupt"] = "true"
            annotations["karpenter.sh/do-not-evict"] = "true"

        bot_container_ephemeral_storage_request = os.getenv("BOT_EPHEMERAL_STORAGE_REQUEST", "10Gi") if not add_webpage_streamer else os.getenv("BOT_EPHEMERAL_STORAGE_REQUEST_IF_WEBPAGE_STREAMER", "9.5Gi")

        bot_container = client.V1Container(
                        name="bot-proc",
                        image=self.image,
                        image_pull_policy="Always",
                        args=command,
                        resources=client.V1ResourceRequirements(
                            requests={
                                "cpu": bot_cpu_request,
                                "memory": os.getenv("BOT_MEMORY_REQUEST", "4Gi"),
                                "ephemeral-storage": bot_container_ephemeral_storage_request
                            },
                            limits={
                                "memory": os.getenv("BOT_MEMORY_LIMIT", "4Gi"),
                                "ephemeral-storage": bot_container_ephemeral_storage_request
                            }
                        ),
                        env_from=[
                            # environment variables for the bot
                            client.V1EnvFromSource(
                                config_map_ref=client.V1ConfigMapEnvSource(
                                    name="env"
                                )
                            ),
                            client.V1EnvFromSource(
                                secret_ref=client.V1SecretEnvSource(
                                    name="app-secrets"
                                )
                            )
                        ],
                        env=[],
                        security_context = client.V1SecurityContext(
                            run_as_non_root=True,
                            run_as_user=1000,                 # matches image USER app
                            run_as_group=1000,                # keep file perms consistent
                            #read_only_root_filesystem=True,
                            #allow_privilege_escalation=False,
                            #capabilities=client.V1Capabilities(drop=["ALL"]),
                            #seccomp_profile=client.V1SeccompProfile(type="RuntimeDefault"),
                        ) 
                    )

        webpage_streamer_container = client.V1Container(
                name="webpage-streamer",
                image=self.image,
                image_pull_policy="Always",
                args=["python", "bots/webpage_streamer/run_webpage_streamer.py"],
                resources=client.V1ResourceRequirements(
                    requests={
                        "cpu": os.getenv("WEBPAGE_STREAMING_CPU_REQUEST", "1"),
                        "memory": os.getenv("WEBPAGE_STREAMING_MEMORY_REQUEST", "4Gi"),
                        "ephemeral-storage": os.getenv("WEBPAGE_STREAMING_EPHEMERAL_STORAGE_REQUEST", "0.5Gi")
                    },
                    limits={
                        "memory": os.getenv("WEBPAGE_STREAMING_MEMORY_LIMIT", "4Gi"),
                        "ephemeral-storage": os.getenv("WEBPAGE_STREAMING_EPHEMERAL_STORAGE_LIMIT", "0.5Gi")
                    }
                ),
                env=[
                    client.V1EnvVar(
                        name="DJANGO_SETTINGS_MODULE",
                        value=os.getenv("DJANGO_SETTINGS_MODULE")
                    ),
                    client.V1EnvVar(name="ALSA_CONFIG_PATH", value="/tmp/asoundrc"),
                ],
                security_context = client.V1SecurityContext(
                    run_as_non_root=True,
                    run_as_user=1000,                 # matches image USER app
                    run_as_group=1000,                # keep file perms consistent
                    #read_only_root_filesystem=True,
                    allow_privilege_escalation=False,
                    capabilities=client.V1Capabilities(drop=["ALL"]),
                    seccomp_profile=client.V1SeccompProfile(type="RuntimeDefault"),
                )                
            )        

        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=bot_name,
                namespace=self.namespace,
                labels=labels,
                annotations=annotations
            ),
            spec=client.V1PodSpec(
                containers=[bot_container],
                restart_policy="Never",
                image_pull_secrets=[
                    client.V1LocalObjectReference(
                        name="regcred"
                    )
                ],
                termination_grace_period_seconds=60,
                # Add tolerations to allow pods to be scheduled on nodes with specific taints
                # This can help with scheduling during autoscaling events
                tolerations=[
                    client.V1Toleration(
                        key="node.kubernetes.io/not-ready",
                        operator="Exists",
                        effect="NoExecute",
                        toleration_seconds=900  # Tolerate not-ready nodes for 15 minutes
                    ),
                    client.V1Toleration(
                        key="node.kubernetes.io/unreachable",
                        operator="Exists",
                        effect="NoExecute",
                        toleration_seconds=900  # Tolerate unreachable nodes for 15 minutes
                    )
                ]
            )
        )

        if add_webpage_streamer:
            webpage_streamer_pod = client.V1Pod(
                metadata=client.V1ObjectMeta(
                    name=f"{bot_name}-webpage-streamer",
                    namespace=self.namespace,
                    labels=labels,
                    annotations=annotations
                ),
                spec=client.V1PodSpec(
                    containers=[webpage_streamer_container],
                    restart_policy="Never",
                    image_pull_secrets=[
                        client.V1LocalObjectReference(
                            name="regcred"
                        )
                    ],
                    termination_grace_period_seconds=60,
                    # Add tolerations to allow pods to be scheduled on nodes with specific taints
                    # This can help with scheduling during autoscaling events
                    tolerations=[
                        client.V1Toleration(
                            key="node.kubernetes.io/not-ready",
                            operator="Exists",
                            effect="NoExecute",
                            toleration_seconds=900  # Tolerate not-ready nodes for 15 minutes
                        ),
                        client.V1Toleration(
                            key="node.kubernetes.io/unreachable",
                            operator="Exists",
                            effect="NoExecute",
                            toleration_seconds=900  # Tolerate unreachable nodes for 15 minutes
                        )
                    ]
                )
            )

        try:
            api_response = self.v1.create_namespaced_pod(
                namespace=self.namespace,
                body=pod
            )

            if add_webpage_streamer:
                webpage_streamer_api_response = self.v1.create_namespaced_pod(
                    namespace=self.namespace,
                    body=webpage_streamer_pod
                )
                logger.info(f"Webpage streamer pod created: {webpage_streamer_api_response}")
            
            return {
                "name": api_response.metadata.name,
                "status": api_response.status.phase,
                "created": True,
                "image": self.image,
                "app_instance": self.app_instance,
                "app_version": self.app_version
            }
            
        except client.ApiException as e:
            return {
                "name": bot_name,
                "status": "Error",
                "created": False,
                "error": str(e)
            }

    def delete_bot_pod(self, pod_name: str) -> Dict:
        try:
            self.v1.delete_namespaced_pod(
                name=pod_name,
                namespace=self.namespace,
                grace_period_seconds=60
            )
            return {"deleted": True}
        except client.ApiException as e:
            return {
                "deleted": False,
                "error": str(e)
            }

# fmt: on
