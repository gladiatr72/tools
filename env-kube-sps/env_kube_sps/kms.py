

from env_kube_sps.util import emit_error
import click


@click.pass_context
def check_key(ctx):
    '''
    check for presense of kms key
    return type: boolean
    '''

    kms = ctx.obj.kms

    ctx.obj.kms_aliases.extend(
        kms.list_aliases()['Aliases']
    )

    check = [
        el
        for el in ctx.obj.kms_aliases
        if el
        and el['AliasName'] == ctx.obj.kms_alias
    ]

    if check:
        ctx.obj.keyid = check[0]['AliasName']
        emit_error(
            'KMS Key, {}, found in {}'.format(
                ctx.obj.kms_alias,
                ctx.obj.mc.region_name
            ),
            color="green"
        )
        return True
    else:
        ctx.obj.keyid = ''
        emit_error(
            'KMS Key, {}, does not exist in {}'.format(
                ctx.obj.kms_alias,
                ctx.obj.mc.region_name
            ),
            color="magenta",
            force=True
        )
        return False

def preflight():

    return check_key

