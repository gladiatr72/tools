# pylint: disable=wrong-import-order,missing-function-docstring,missing-class-docstring,missing-module-docstring,no-value-for-parameter,invalid-name

from env_kube_sps.util import emit_error, get_eks_token
import env_kube_sps.kube as kube
import env_kube_sps.sps as sps
import kubernetes as K
import click


@click.pass_context
def check_cluster(ctx):

    cluster_name = ctx.params['cluster_name']
    eks = ctx.obj.eks

    if cluster_name not in ctx.obj.eks_clusters.keys():
        try:
            cluster_list = eks.list_clusters()['clusters']

            if cluster_name in cluster_list:
                ctx.obj.eks_clusters.update(
                    {
                        cluster_name: eks.describe_cluster(name=cluster_name)['cluster']
                    }
                )

        except eks.exceptions.ClientError:
            emit_error(
                'Access to IAM EKS:ListClusters required for this operation',
                color='bright_white',
                force=True
            )

            return False
    return True

@click.pass_context
def _kubeconfig(ctx):

    cluster_name = ctx.params['cluster_name']
    cluster = ctx.obj.eks_clusters[cluster_name]

    token = get_eks_token()['status']['token']

    return {
        'apiVersion': 'v1',
        'kind': 'Config',
        'clusters': [
            {
                'name': cluster_name,
                'cluster': {
                    'certificate-authority-data': cluster['certificateAuthority']['data'],
                    'server': cluster['endpoint']
                }
            }
        ],
        'contexts': [
            {
                'name': 'this',
                'context': {
                    'cluster': cluster_name,
                    'user': cluster_name,
                    'namespace': ctx.params['namespace']
                }
            }
        ],
        'current-context': 'this',
        'preferences': {},
        'users': [
            {
                'name': cluster_name,
                'user': {
                    'token': token
                }
            }
        ]
    }

@click.pass_context
def check_namespace(ctx):
    try:
        ctx.obj.kv1.read_namespace(ctx.params['namespace'])
    except K.client.exceptions.ApiException:
        emit_error(
            'namespace, {}, does not exist'.format(ctx.params['namespace']),
            force=True,
            color='red'

        )
        return False

    return True


@click.pass_context
def preflight(ctx):
    if not check_cluster():
        return False

    K.config.load_kube_config_from_dict(_kubeconfig())
    ctx.obj.kv1 = K.client.CoreV1Api()
    ctx.obj.kauthv1 = K.client.AuthorizationV1Api()

    if not kube.check_rbac('secrets'):
        return False

    if not check_namespace():
        return False

    return True


@click.pass_context
def sync(ctx):

    k_namespace = ctx.params['namespace']
    component = ctx.parent.params['component']
    sps_labels = ctx.params['with_label']

    if not sps_labels:
        sps_labels = ['staged']

    param_objects = sps.parameters_by_label(sps_labels, refresh=True)

    params = '\n'.join([
        '='.join(
            (el['Name'].split('/')[-1], el['Value'],)
        ) for el in param_objects
    ])

    param_data = {'environment': params}

    secret_name = '{}-env'.format(component)

    secret_obj = kube.secret(secret_name, param_data)

    try:
        ctx.obj.kv1.create_namespaced_secret(
            namespace=k_namespace,
            body=secret_obj
        )

        emit_error(
            'secret, {}, created in namespace {}'.format(secret_name, k_namespace),
            force=True,
            color="green"
        )
    except K.client.exceptions.ApiException as e:
        if e.reason == 'Conflict':
            ctx.obj.kv1.patch_namespaced_secret(  # noqa
                name=secret_name,
                namespace=k_namespace,
                body=secret_obj
            )

        emit_error(
            'secret, {}, updated in namespace {}'.format(secret_name, k_namespace),
            force=True,
            color="green"
        )
