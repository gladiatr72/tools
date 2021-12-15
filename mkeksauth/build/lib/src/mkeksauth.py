#!/usr/bin/env python
# pylint: disable=C0103,C0116
"""
Its purpose is to create the aws-auth configmap that grants access
to an EKS cluster.
"""

import io
import re
import selectors
import copy
from typing import List, Dict, Any, Tuple, AnyStr
from kubernetes import client, config  # type: ignore
import boto3  # type: ignore
import yaml
import click
import json

DOCUMENT = {
    "apiVersion": "v1",
    "kind": "ConfigMap",
    "metadata": {"name": "aws-auth", "namespace": "kube-system"},
    "data": {"mapRoles": "", "mapUsers": ""},
}


class CtxObject:
    pass


class EksAuth(object):
    """
    EksAuth(cluster_name)

    Provides utility for setting up output for the EKS aws_auth controller
    that is also human readable.
    """

    users: List[Dict[str, Any]] = []
    roles: List[Dict[str, Any]] = []

    _valid = {
        "cluster_name": False,
        "cluster_exists": False,
    }

    def __init__(
        self,
        cluster_name: str,
        context: str,
        group: Tuple[Tuple[str, str]],
        user: Tuple[Tuple[str, str]],
        role: Tuple[Tuple[str, str]],
        verbose: bool,
        output_file,
        apply: bool,
    ):

        self.context = context

        try:
            config.load_kube_config(context=context)
        except config.ConfigException:
            raise click.BadParameter(
                "client configuration for cluster {} not found (~/.kube/config)".format(
                    cluster_name
                )  # noqa
            )

        self._cluster_name = cluster_name
        self.mc = boto3.Session()
        yaml.add_representer(str, self._yaml_str_format)

        self._set_cluster_role_arn()
        self._load_node_role()
        self._users_from_groups(group)
        self._build_roles(role)
        self._doc = copy.deepcopy(DOCUMENT)

        self._doc["data"]["mapRoles"] = self._yaml_out(self.roles)  # type: ignore
        if self.users:
            self._doc["data"]["mapUsers"] = self._yaml_out(self.users)  # type: ignore
        else:
            self._doc["data"].pop("mapUsers")  # type: ignore

    def render(self, fh=None):
        return self._yaml_out(self._doc, fh)

    def apply(self, namespace="kube-system"):
        """
        apply aws-auth configmap to EKS cluster
        """
        mc = client.CoreV1Api()

        configmaps = mc.list_namespaced_config_map(namespace).items
        if "aws-auth" in [el.metadata.name for el in configmaps]:
            mc.replace_namespaced_config_map(
                name="aws-auth", body=self._doc, namespace=namespace
            )
        else:
            mc.create_namespaced_config_map(body=self._doc, namespace=namespace)

    @property
    def cluster_name(self):
        """
        By default, `aws eks update-kubeconfig` creates a kube client context
        with the cluster arn as the _name_ key (_name_ being the sole search
        key for retrieving EKS cluster data)  The simplest solution is to
        make use of the `--alias` flag with the above invocation to set the
        name of the kube context to the name of the cluster.

        The following makes this matter less.

        Note: this completely falls apart if the context is not either the
        full arn or the name of the cluster.
        """

        retval = self._cluster_name
        if not self._valid["cluster_name"]:
            rex_arn = re.compile(
                r"arn:aws:eks:[^:]+:[\d]+:cluster/(?P<cluster_name>.*)"
            )
            res_arn = rex_arn.search(self._cluster_name)

            if res_arn and "cluster_name" in res_arn.groupdict():
                self._cluster_name = res_arn.groupdict()["cluster_name"]
                retval = self._cluster_name

            self._valid["cluster_name"] = True

        return retval

    def _load_node_role(self) -> None:
        rc = self.mc.resource("ec2")
        rc_iam = self.mc.resource("iam")

        instances = rc.instances.filter(
            Filters=[
                {
                    "Name": "tag:kubernetes.io/cluster/{}".format(self._cluster_name),
                    "Values": ["owned"],
                }
            ]
        )

        node_roles = {
            role.arn
            for instance in instances
            if instance.state["Name"] == "running"
            for attached_profile_arn in [instance.iam_instance_profile["Arn"]]
            for profile in rc_iam.instance_profiles.all()
            if attached_profile_arn == profile.arn
            for role in profile.roles
        }

        for node_role in node_roles:
            self.roles.append(
                {
                    "rolearn": node_role,
                    "username": "system:node:{{EC2PrivateDNSName}}",
                    "groups": ["system:masters"],
                }
            )

    def _build_roles(self, roles: Tuple[Tuple[str, str]]) -> None:
        rc = self.mc.resource("iam")

        roles_ = [
            {"rolearn": role.arn, "username": role.name, "groups": [k8s_group]}
            for iam_role, k8s_group in roles
            for role in rc.roles.all()
            if role.name == iam_role
        ]

        self.roles.extend(roles_)

    def _users_from_groups(self, groups: Tuple[Tuple[str, str]]) -> None:

        # provided with an AWS IAM group name, retrieve and process
        # member users' records

        rc = self.mc.resource("iam")

        assignments = [
            {"userarn": user.arn, "username": user.name, "groups": [k8s_group]}
            for aws_group in rc.groups.all()
            for iam_group, k8s_group in groups
            for user in aws_group.users.all()
            if aws_group.name == iam_group
        ]

        self.users.extend(assignments)

    @classmethod
    def _extract_kube_groups(self):

        mc = client.RbacAuthorizationV1Api()

        roles = mc.list_cluster_role_binding().items
        roles.extend(mc.list_role_binding_for_all_namespaces().items)

        retval = {  # noqa
            subject.name
            for rb in roles
            if rb.subjects is not None
            for subject in rb.subjects
            if subject.kind == "Group"
        }

        return retval

    @classmethod
    def _extract_kube_users(self):

        mc = client.RbacAuthorizationV1Api()
        retval = {  # noqa
            subject.name
            for rb in mc.list_cluster_role_binding().items
            if rb.subjects is not None
            for subject in rb.subjects
            if subject.kind == "User"
        }

        return retval

    @property
    def region(self) -> str:

        return self.mc.region_name if self.mc.region_name else 'us-east-1'

    @property
    def kube_rbac_groups(self):
        """
        introspect any clusterrolebindings defined on the given cluster to
        discover what groups are defined
        """
        if not getattr(self, "_kube_rbac_groups", None):
            self._kube_rbac_groups = self._extract_kube_groups()
        return self._kube_rbac_groups

    @property
    def kube_rbac_users(self):
        """
        introspect any clusterrolebindings defined on the given cluster to
        discover what users are defined
        """
        if not getattr(self, "_kube_rbac_users", None):
            self._kube_rbac_users = self._extract_kube_users()
        return self._kube_rbac_users

    def _set_cluster_role_arn(self):
        """ retrieves the roleArn assigned to the given eks cluster """

        rc = self.mc.client("eks")
        try:
            this = rc.describe_cluster(name=self.cluster_name)
            self._valid["cluster_exists"] = True
        except rc.exceptions.ResourceNotFoundException:
            raise click.exceptions.BadParameter(
                message="eks cluster, {}, not found".format(self.cluster_name)
            )
        #except:
        #    raise click.exceptions.UsageError([self.cluster_name, self.context, rc._endpoint])

        self.cluster_role_arn = this["cluster"]["roleArn"]

    @property
    def account(self) -> str:
        """provides current aws account number"""

        retval = None
        if not getattr(self, "_account", None):
            rc = self.mc.client("sts")
            retval = rc.get_caller_identity()["Account"]
            self._account = retval
        else:
            retval = self._account

        return retval

    @classmethod
    def _yaml_out(cls, content, fh=None) -> None:

        if fh:
            yaml.dump(content, fh, sort_keys=False)

        fh = io.StringIO()
        yaml.dump(content, fh, sort_keys=False)
        fh.seek(0)
        retval = fh.read()

        return retval

    @classmethod
    def _yaml_str_format(cls, dumper, content: str):
        retval = None

        if len(content.splitlines()) > 1:
            retval = dumper.represent_scalar(
                "tag:yaml.org,2002:str", content, style="|"
            )
        else:
            retval = dumper.represent_scalar("tag:yaml.org,2002:str", content)

        return retval


@click.pass_context
def _ingest_groups(ctx: click.Context, role: AnyStr, members: List) -> bool:
    ctx.params["group"] += tuple([(group, role) for group in members])

    return True


@click.pass_context
def _ingest_roles(ctx: click.Context, role: AnyStr, members: List) -> bool:
    ctx.params["role"] = tuple([(role, role) for role in members])

    return True


@click.pass_context
def _ingest_users(ctx: click.Context, role: AnyStr, members: List) -> bool:
    return True


@click.pass_context
def _ingest_cluster_name(ctx: click.Context, _, name: AnyStr) -> bool:

    if not ctx.params["cluster_name"]:
        ctx.params["cluster_name"] = name

    return True


@click.pass_context
def _ingest_json_config(ctx) -> bool:
    ingestors = {
        "iam-groups": _ingest_groups,
        "iam-users": _ingest_users,
        "iam-roles": _ingest_roles,
        "cluster-name": _ingest_cluster_name,
    }

    for el in ctx.obj.inbound:
        try:
            role = el.pop("role")
        except AttributeError:
            continue
        for perm_type, members in el.items():
            try:
                ingestors[perm_type](role, members)  # type: ignore
            except KeyError:
                click.secho(f"invalid option type: {perm_type}", err=True, fg="yellow")
                pass

    return True


def _import_json_config(ctx) -> bool:
    retval = True

    try:
        ctx.obj.inbound = json.loads(ctx.obj.inbound_raw)
    except json.JSONDecodeError:
        retval = False

    return retval


def _read(fh, mask):
    return fh.read()


@click.pass_context
def check_stdin(ctx: click.Context) -> bool:
    """
    check stdin for incoming JSON configuration
    """

    retval = False
    ctx.obj.inbound_raw = "[]"

    fh = click.open_file("-", "r")
    ctx.obj.sel = selectors.DefaultSelector()
    ctx.obj.sel.register(fh, selectors.EVENT_READ, _read)

    events = ctx.obj.sel.select(timeout=1.5)

    if events:
        selector_key, mask = events[0]
        func = selector_key.data
        ctx.obj.inbound_raw = func(selector_key.fileobj, mask)
        retval = _import_json_config(ctx)

    return retval


@click.group(invoke_without_command=True)
@click.option("--cluster-name", envvar="KUBE_CLUSTER", required=False)
@click.option(
    "--context",
    required=False,
    metavar="kube context name"
)
@click.option(
    "--group",
    type=(str, str),
    metavar="<AWS IAM Group Name> <kubernetes RBAC clusterrole>",
    multiple=True,
)
@click.option(
    "--user",
    type=(str, str),
    metavar="<AWS IAM User Name> <kubernetes RBAC clusterrole>",
    multiple=True,
)
@click.option(
    "--role",
    type=(str, str),
    metavar="<AWS IAM Role Name> <kubernetes RBAC clusterrole>",
    multiple=True,
)
@click.option("--verbose", is_flag=True, default=False)
@click.option("--output-file", type=click.File("w"), default="-")
@click.option("--apply", is_flag=True, help="Auto-apply aws-auth configmap to cluster")
@click.pass_context
def cli(ctx, cluster_name, context, group, user, role, verbose, output_file, apply):
    """
    Create the EKS/aws-auth configmap

    \b
    ex: mkawsauth \\
            --group ORG-ADMIN-GROUP system:masters \\
            --group ORG-NONADMIN-GROUP system:authenticated \\
            --role test-role system:authenticated \\
            --output-file /tmp/aws-auth.yaml
    """
    ready = True

    ctx.obj = CtxObject

    if check_stdin():
        _ingest_json_config()

    if not ctx.invoked_subcommand:
        if not (ctx.params["group"] or ctx.params["role"]):
            click.secho("at least one --role or --group is required\n", fg="yellow")
            ready = False

        if not ctx.params["cluster_name"]:
            click.secho("--cluster-name is required\n", fg="yellow")
            ready = False

        if ready:
            ctx.obj = EksAuth(**ctx.params)
            ctx.obj.context = context

            if output_file.name == "<stdout>":
                if verbose:
                    ctx.obj.render(output_file)
                else:
                    click.echo(
                        "Output file not specified. Use --verbose for visual output"
                    )
            else:
                click.secho(
                    "Writing EKS auth bits to {}".format(output_file.name),
                    err=True,
                    fg="white",
                )

            if apply:
                click.secho(
                    "Applying EKS auth bits to {} in {}".format(
                        ctx.obj.cluster_name, ctx.obj.region
                    ),
                    err=True,
                    fg="white",
                    bg="red",
                )
                ctx.obj.apply()
        else:
            click.echo(ctx.command.get_help(ctx))


@click.pass_context
def _kube_rbac_groups(ctx):

    if not ctx.parent.params["cluster_name"]:
        click.echo(ctx.parent.get_help())
        click.secho(
            "\n--cluster-name required for this operation", fg="yellow", err=True
        )
        return []
    else:
        ctx.obj = EksAuth(**ctx.parent.params)
        return ctx.obj.kube_rbac_groups


@click.pass_context
def _kube_rbac_users(ctx):

    if not ctx.parent.params["cluster_name"]:
        click.echo(ctx.parent.get_help())
        click.secho(
            "\n--cluster-name required for this operation", fg="yellow", err=True
        )
        return []
    else:
        ctx.obj = EksAuth(**ctx.parent.params)
        return ctx.obj.kube_rbac_users


@cli.command()
@click.pass_context
def list_kube_rbac_users(ctx):

    _ = [click.echo(el) for el in _kube_rbac_users()]


@cli.command()
@click.pass_context
def list_kube_rbac_groups(ctx):

    _ = [click.echo(el) for el in _kube_rbac_groups()]


@cli.command()
@click.pass_context
def list_aws_roles(ctx):

    mc = boto3.Session()
    rc = mc.resource("iam")

    _ = [click.echo(role.name) for role in rc.roles.all()]


@cli.command()
@click.pass_context
def list_aws_users(ctx):

    mc = boto3.Session()
    rc = mc.resource("iam")

    _ = [click.echo(user.name) for user in rc.users.all()]


@cli.command()
@click.pass_context
def list_aws_groups(ctx):

    mc = boto3.Session()
    rc = mc.resource("iam")

    for group in rc.groups.all():
        click.echo(group.name)
        for user in group.users.all():
            click.echo("\t{}".format(user.arn))
