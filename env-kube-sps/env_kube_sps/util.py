
import base64
import json
import re
from pprint import PrettyPrinter

from datetime import datetime, timedelta
from botocore.signers import RequestSigner
from botocore.model import ServiceId

import botocore
import click


AUTH_SERVICE = "sts"
AUTH_COMMAND = "GetCallerIdentity"
AUTH_API_VERSION = "2011-06-15"
AUTH_SIGNING_VERSION = "v4"

# Presigned url timeout in seconds
URL_TIMEOUT = 60

TOKEN_EXPIRATION_MINS = 14

TOKEN_PREFIX = 'k8s-aws-v1.'

CLUSTER_NAME_HEADER = 'x-k8s-aws-id'

KEY_VALUE_REX = re.compile(r'^\s*([^=]+)\s*=\s*(.+)\s*$')


@click.pass_context
def secret_labels(ctx):
    '''
    `click.option(multiple=True)` allows for an option to be submitted
    multiple times with values aggregated into a tuple.

    this program takes its k/v pairs as `K=V` string patterns that
    this function converts to a dictioary for use in building kubernetes
    secret labels.
    '''

    return {
        k: v
        for el in ctx.params['with_label']
        for k, v in KEY_VALUE_REX.findall(el)
    }

@click.pass_context
def whoami(ctx):

    return ctx.obj.sts.get_caller_identity()['Arn']


def dict2tags(tagdict):
    '''
    takes python dictionary and returns AWS tag bags
    '''
    return [
        {'Key': k, 'Value': v}
        for k, v in tagdict.items()
    ]


def chunk_sequence(seq, limit=10):
    '''
    generator that yields lists of _limit_ number of elements from a sequence
    until sequence exhausted
    '''
    top = 0

    chunks = range(0, len(seq), limit)

    for el in chunks:
        yield seq[top: el+limit]
        top += limit

@click.pass_context
def emit_error(ctx, msg, force=False, color="white", **kwargs):
    '''
    args:
        msg: (str) message
        force: (bool: default: False)  If False, emit message
               only if `--verbose`
        color: see docs for `click.secho()`
        kwargs: (dict) additional args to pass to `click.secho()`
    '''

    if (ctx.obj.main['verbose'] or force):
        click.secho(str(msg), fg=color, err=True, **kwargs)


pretty = PrettyPrinter(depth=20, width=100, indent=4).pformat


'''
from awscli-v1

customizations/eks/get_token.py
'''


def get_expiration_time():
    token_expiration = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRATION_MINS)
    return token_expiration.strftime('%Y-%m-%dT%H:%M:%SZ')

@click.pass_context
def get_eks_token(ctx):

    client_factory = STSClientFactory(ctx.obj.mc._session)

    sts_client = client_factory.get_sts_client(
        region_name=ctx.obj.mc.region_name,
        role_arn=ctx.params['assume_role'])

    token = TokenGenerator(sts_client).get_token(ctx.params['cluster_name'])

    # By default STS signs the url for 15 minutes so we are creating a
    # rfc3339 timestamp with expiration in 14 minutes as part of the token, which
    # is used by some clients (client-go) who will refresh the token after 14 mins
    token_expiration = get_expiration_time()

    full_object = {
        "kind": "ExecCredential",
        "apiVersion": "client.authentication.k8s.io/v1alpha1",
        "spec": {},
        "status": {
            "expirationTimestamp": token_expiration,
            "token": token
        }
    }

    return full_object

class TokenGenerator(object):
    def __init__(self, sts_client):
        self._sts_client = sts_client

    def get_token(self, cluster_name):
        """ Generate a presigned url token to pass to kubectl. """
        url = self._get_presigned_url(cluster_name)
        token = TOKEN_PREFIX + base64.urlsafe_b64encode(
            url.encode('utf-8')).decode('utf-8').rstrip('=')
        return token

    def _get_presigned_url(self, cluster_name):
        return self._sts_client.generate_presigned_url(
            'get_caller_identity',
            Params={'ClusterName': cluster_name},
            ExpiresIn=URL_TIMEOUT,
            HttpMethod='GET',
        )


class STSClientFactory(object):
    def __init__(self, session):
        self._session = session

    def get_sts_client(self, region_name=None, role_arn=None):
        client_kwargs = {
            'region_name': region_name
        }
        if role_arn is not None:
            creds = self._get_role_credentials(region_name, role_arn)
            client_kwargs['aws_access_key_id'] = creds['AccessKeyId']
            client_kwargs['aws_secret_access_key'] = creds['SecretAccessKey']
            client_kwargs['aws_session_token'] = creds['SessionToken']
        sts = self._session.create_client('sts', **client_kwargs)
        self._register_cluster_name_handlers(sts)
        return sts

    def _get_role_credentials(self, region_name, role_arn):
        sts = self._session.create_client('sts', region_name)
        return sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName='EKSGetTokenAuth'
        )['Credentials']

    def _register_cluster_name_handlers(self, sts_client):
        sts_client.meta.events.register(
            'provide-client-params.sts.GetCallerIdentity',
            self._retrieve_cluster_name
        )
        sts_client.meta.events.register(
            'before-sign.sts.GetCallerIdentity',
            self._inject_cluster_name_header
        )

    def _retrieve_cluster_name(self, params, context, **kwargs):
        if 'ClusterName' in params:
            context['eks_cluster'] = params.pop('ClusterName')

    def _inject_cluster_name_header(self, request, **kwargs):
        if 'eks_cluster' in request.context:
            request.headers[
                CLUSTER_NAME_HEADER] = request.context['eks_cluster']
