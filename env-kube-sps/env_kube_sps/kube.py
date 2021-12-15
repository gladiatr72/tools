import click
import kubernetes as K
from env_kube_sps.util import emit_error, secret_labels, whoami

@click.pass_context
def secret(ctx, name, secrets):
    '''
    name: str
    secrets: tuple(tuple(str, str),)
    '''

    labels = secret_labels()

    labels.update({
        'heritage': __package__,
        'environment': ctx.parent.params['environment']
    })

    retval = K.client.V1Secret(
        type="opaque",
        metadata={'name': name, 'labels': labels},
        string_data=secrets
    )

    return retval

@click.pass_context
def check_rbac(ctx, kind):
    '''
    kind: Kubernetes object _kind_ (e.g.: deployment, daemonset, secret, etc)
    '''

    retval = True

    for action in ('create', 'update', 'delete', 'list'):

        access_review_secret_spec = K.client.V1SelfSubjectAccessReviewSpec(
            resource_attributes={
                "namespace": ctx.params['namespace'],
                "verb": action,
                "resource": kind.lower(),
            }
        )


        access_review_secret = K.client.V1SelfSubjectAccessReview(
            api_version='authorization.k8s.io/v1',
            kind="SelfSubjectAccessReview",
            metadata={"creationTimestamp": None},
            spec=access_review_secret_spec,
            status={"allowed": False}
        )

        try:
            res = ctx.obj.kauthv1.create_self_subject_access_review(
                body=access_review_secret
            )
        except K.client.ApiException:
            emit_error(
                '{} is not authorized for connection with {}'.format(
                    whoami(),
                    ctx.params['cluster_name']
                ),
                force=True,
                color="red"
            )
            return False

        if not res.status.allowed:
            emit_error(
                "{} {} in namespace, {}, not authorized".format(
                    action,
                    kind.title(),
                    ctx.params['namespace'],
                ),
                force=True,
                color="magenta"
            )
            retval = False
        else:

            emit_error(
                "{} {} in namespace, {}, authorized".format(
                    action,
                    kind,
                    ctx.params['namespace']
                ),
                color="green"
            )

    return retval
