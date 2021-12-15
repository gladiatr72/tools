
import re
import time

import click
import env_kube_sps.kms as kms
from .util import emit_error, dict2tags, pretty, KEY_VALUE_REX, chunk_sequence
from botocore.exceptions import ClientError


@click.pass_context
def parameters_list(ctx, param_path, refresh=False):
    '''
    Capped at 10 elements/api-call, so, this.
    '''

    if refresh or not ctx.obj.parameters:
        ssm = ctx.obj.ssm

        args = {'Path': param_path, 'WithDecryption': True, 'Recursive': True}

        while True:
            res = ssm.get_parameters_by_path(**args)

            ctx.obj.parameters.update({
                param['Name']: param
                for param in res['Parameters']
            })

            if res.get('NextToken', None):
                args['NextToken'] = res['NextToken']
            else:
                break

    return [el for el in tuple(ctx.obj.parameters.keys()) if el.startswith('/')]


@click.pass_context
def parameter_history(ctx, param_path, refresh=True):

    if param_path in ctx.obj.parameters:
        if param_path not in ctx.obj.parameter_history.keys():

            args = {'Name': param_path}
            args.update({'WithDecryption': True})

            while True:
                try:
                    res = ctx.obj.ssm.get_parameter_history(**args)
                except ClientError as e:
                    emit_error(e, force=True, color='red')

                ctx.obj.parameter_history.update({param_path: res['Parameters']})

                if res.get('NextToken', None):
                    args['nextToken'] = res['NextToken']
                else:
                    break

    return ctx.obj.parameter_history[param_path]


@click.pass_context
def parameter_labels_list(ctx, refresh=False):

    if not ctx.obj.parameter_labels:
        ctx.obj.parameter_labels = {
            label
            for p in parameters_list('/')
            for pver in parameter_history(p)
            if pver.get('Labels', [])
            for label in pver['Labels']
        }

    return ctx.obj.parameter_labels


@click.pass_context
def parameters_by_label(ctx, labels, refresh=False):

    param_path = ctx.obj.sps_prefix

    retval = [
        pver
        for p in parameters_list(param_path, refresh=refresh)
        for pver in parameter_history(p, refresh=refresh)
        for l in labels      # noqa
        if l in pver['Labels']
    ]

    return retval

@click.pass_context
def check_parameter(ctx, param_path, refresh=False):
    '''
    args:
      param_path: full name/path for SSM Parameter Store
      refresh: (bool) if True, refresh local data for given parameter

    return: (bool) True if present
    possible side-effects:
      cache unencrypted value in ctx.obj.parameters{} for comparing
      submitted and stored values. (prevents creating a new parameter value
      **version** when value unchanged)
    '''
    ssm = ctx.obj.ssm

    try:
        if param_path not in ctx.obj.parameters.keys():
            res = ssm.get_parameter(Name=param_path, WithDecryption=True)
            ctx.obj.parameters.update({param_path: res['Parameter']})

        return True
    except ssm.exceptions.ParameterNotFound:

        return False


@click.pass_context
def purge(ctx):

    pattern = ctx.params['regex']
    param_prefix = '/{environment}/{component}'.format(**ctx.parent.params)

    rex = re.compile(r'^{}/({})'.format(param_prefix, pattern), re.I)

    params = [
        el
        for el in parameters_list(param_prefix, refresh=True)
        if rex.search(el)
    ]

    try:
        for batch in chunk_sequence(params):
            ctx.obj.ssm.delete_parameters(Names=batch)

        for el in params:
            emit_error('{} deleted'.format(el), color="magenta", force=True)
    except ctx.obj.ssm.exceptions.ClientError as e:
        emit_error(e, force=True)
        emit_error('failed deletion', color="yellow", force=True)


@click.pass_context
def ingest(ctx):

    AUTO_VARS = [
        'LANG',
        'LOGNAME',
        'HOME',
        'PATH',
        'TZ',
        'USER',
        'SHELL'
    ]

    if ctx.params['input_file']:
        ctx.obj.raw = ctx.params['input_file'].read().split("\n")

        ctx.obj.env_variables = {
            K: V
            for el in ctx.obj.raw
            if el
            and KEY_VALUE_REX.search(el)
            for K, V in KEY_VALUE_REX.findall(el)
            if K not in AUTO_VARS
        }
    else:
        ctx.obj.raw = []

        ctx.obj.env_variables = {
            K: V
            for el in ctx.params['set_key']
            for K, V in KEY_VALUE_REX.findall(el)
        }

    emit_error(
        '{} variables ingested'.format(len(ctx.obj.env_variables)),
        force=True
    )

@click.pass_context
def sync(ctx):
    '''
    args: (none)
    returns: (none)

    side-effects:
      store and tag ingested key/value pairs in SSM parameter store
      using he pattern `/[environment]/[component]/[Key Name]

    '''
    ssm = ctx.obj.ssm
    component = ctx.obj.main['component']
    env = ctx.obj.main['environment']
    update = ctx.params['update']
    is_secret = ctx.params['secret']

    path_prefix = ctx.obj.sps_prefix

    for K, V in ctx.obj.env_variables.items():

        kwargs = {}

        param_path = '{}/{}'.format(path_prefix, K)

        tags = dict2tags({
            'Name': K,
            'component': component,
            'environment': env,
            'Managed-By': 'env-kube-sps'
        })

        if check_parameter(param_path):
            emit_error('{} found'.format(param_path), color="green")

            if not update:
                emit_error('{}: exists and --update=False'.format(param_path))
                continue
            else:
                if V == ctx.obj.parameters[param_path]['Value']:
                    emit_error('{}: unchanged.  Skipping...'.format(param_path))
                    continue

                emit_error('Updating {}...'.format(param_path), force=True)
                kwargs.update({'Overwrite': True})
        else:
            emit_error(
                '{} not found. Creating...'.format(param_path),
                color="green",
                force=True
            )
            kwargs.update({'Tags': tags})

        kwargs.update({
            'Name': param_path,
            'Value': V,
        })

        if is_secret:
            kwargs.update({
                'Type': 'SecureString',
                'KeyId': ctx.obj.keyid
            })
        else:
            kwargs.update({
                'Type': 'String'
            })

        if len(V) > 4096:
            kwargs.update({
                'Tier': 'Advanced'
            })

        res = ssm.put_parameter(**kwargs)

        # ^ this isn't always ready by the time it returns, so...
        while True:
            try:
                ssm.label_parameter_version(
                    Name=param_path,
                    ParameterVersion=res['Version'],
                    Labels=(ctx.params['with_label'],)
                )
                break
            except ssm.exceptions.ParameterNotFound:
                time.sleep(0.1)


@click.pass_context
def preflight(ctx):

    input_file = ctx.params['input_file']
    set_key = ctx.params['set_key']

    if input_file and set_key:
        emit_error(
            '--input-file and --set-key are exclusive',
            color="yellow",
            force=True
        )
        return False
    elif not (input_file or set_key):
        emit_error(
            '--input-file or --set-key required',
            force=True,
            color="yellow",
        )
        return False

    if len(ctx.params['with_label']) > 8:
        emit_error(
            'custom parameter labels limited to 10',
            force=True,
            color=-"yellow")
        return False

    if not kms.check_key():
        return False

    return True

