#!/usr/bin/env python


import sys
import re
import os
from io import StringIO
import logging

from collections import defaultdict

from .util import emit_error, get_eks_token
import env_kube_sps.sps as sps
import env_kube_sps.eks as eks
import env_kube_sps.kms as kms

import click
import boto3

class Ctx:
    '''
    Context Data Container Class
    '''

    def __init__(self):
        self.parameters = dict()
        self.parameter_history = dict()
        self.parameter_labels = set()
        self.kms_aliases = list()
        self.eks_clusters = dict()

        self.mc = boto3.Session()

        self.kms = self.mc.client('kms')
        self.ssm = self.mc.client('ssm')
        self.eks = self.mc.client('eks')
        self.sts = self.mc.client('sts')
        self.sps_prefix = str()
        self.keyid = str()


@click.group()
@click.option('--environment', envvar='BOVISYNC_ENVIRONMENT', required=True)
@click.option('--component', envvar='BOVISYNC_COMPONENT', required=True)
@click.option('-v', '--verbose', is_flag=True, default=False)
@click.pass_context
def main(ctx, environment, component, verbose):  # , update, set_key, input_file):

    ctx.obj = Ctx()

    ctx.obj.kms_alias = 'alias/{}/ssm'.format(environment)
    ctx.obj.sps_prefix = '/{environment}/{component}'.format(**ctx.params)

    ctx.obj.main = ctx.params


@main.command()
@click.option('--update', is_flag=True, default=False)
@click.option('-k', '--set-key',
              metavar="<ENV_VAR_NAME>=<ENV_VAR_VALUE>",
              multiple=True)
@click.option('--input-file', type=click.File('r'))
@click.option('--with-label', default='staged')
@click.option('--secret', default=True, type=bool)
@click.pass_context
def sync_to_sps(ctx, update, set_key, input_file, with_label, secret):

    if (secret and kms.preflight()):
        ctx.meta['keyid'] = ctx.obj.keyid

    if sps.preflight():
        sps.ingest()
        sps.sync()

@main.command()
@click.confirmation_option(prompt='Confirm')
@click.option('-e', '--regex', help='applies only to rightmost sps path element')
def purge_sps(regex):

    sps.purge()

@main.command()
@click.option('--regex', default='.*$', help='applies only to rightmost sps path element')
@click.pass_context
def list_sps(ctx, regex):

    param_prefix = '/{environment}/{component}'.format(**ctx.parent.params)
    rex = re.compile(r'^{}/({})'.format(param_prefix, regex), re.I)
    parameters = sps.parameters_list(param_prefix)
    parameters.sort()

    [
        emit_error(el.split('/')[-1], force=True)
        for el in parameters
        if rex.search(el)
    ]


@main.command()
@click.option('-c', '--cluster-name', required=True)
@click.option('-n', '--namespace', envvar='KUBE_NAMESPACE', required=True)
@click.option('-r', '--assume-role', required=False)
@click.option('--with-label', multiple=True, required=False)
@click.pass_context
def sync_to_eks(ctx, cluster_name, namespace, assume_role, with_label):

    if not eks.preflight():
        emit_error(
            '''
            EKS preflight checks did not succeed. Please re-run using --verbose
            for details.
            ''',
            force=True,
            color="magenta"
        )
        sys.exit(2)

    ctx.obj.sps_prefix = ctx.find_root().obj.sps_prefix

    eks.sync()
