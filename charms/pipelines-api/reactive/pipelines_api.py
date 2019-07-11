import os

import yaml
from charms import layer
from charms.reactive import set_flag, clear_flag, when, when_not, hookenv


@when('charm.pipelines-api.started')
def charm_ready():
    layer.status.active('')


@when('pipelines-api.available')
def configure_http(http):
    http.configure(port=hookenv.config('http-port'), hostname=hookenv.application_name())


@when('layer.docker-resource.oci-image.changed', 'config.changed')
def update_image():
    clear_flag('charm.pipelines-api.started')


@when('layer.docker-resource.oci-image.available', 'mysql.connected', 'minio.available')
@when_not('charm.pipelines-api.started')
def start_charm(mysql, minio):
    layer.status.maintenance('configuring container')

    image_info = layer.docker_resource.get_info('oci-image')
    service_name = hookenv.service_name()

    grpc_port = hookenv.config('grpc-port')
    http_port = hookenv.config('http-port')

    layer.caas_base.pod_spec_set(
        {
            'service': {
                'annotations': {
                    'getambassador.io/config': yaml.dump_all(
                        [
                            {
                                'apiVersion': 'ambassador/v0',
                                'kind': 'Mapping',
                                'name': 'pipeline-api',
                                'prefix': '/apis/v1beta1/pipelines',
                                'rewrite': '/apis/v1beta1/pipelines',
                                'service': f'{service_name}:{http_port}',
                                'use_websocket': True,
                                'timeout_ms': 30000,
                            }
                        ]
                    )
                }
            },
            'containers': [
                {
                    'name': 'pipelines-api',
                    'imageDetails': {
                        'imagePath': image_info.registry_path,
                        'username': image_info.username,
                        'password': image_info.password,
                    },
                    'ports': [
                        {'name': 'grpc', 'containerPort': grpc_port},
                        {'name': 'http', 'containerPort': http_port},
                    ],
                    'config': {
                        'MYSQL_SERVICE_HOST': 'mariadb',
                        'MYSQL_SERVICE_PORT': 3306,
                        'MINIO_SERVICE_SERVICE_HOST': minio.all_joined_units[0].application_name,
                        'MINIO_SERVICE_SERVICE_PORT': minio.all_joined_units[0].received['port'],
                        'POD_NAMESPACE': os.environ['JUJU_MODEL_NAME'],
                        'InitConnectionTimeout': 20,
                    },
                }
            ],
        }
    )

    layer.status.maintenance('creating container')
    set_flag('charm.pipelines-api.started')