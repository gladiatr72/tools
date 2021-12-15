
import os

import yaml
import click

__version__ = "1.0.0"


class CtxObject:
    pass


@click.group(invoke_without_command=True)
@click.option("--output_path", "-o", default=".")
@click.option("--bundle", "-i", type=click.File("r"), default='-')
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def run(ctx, output_path, bundle, verbose):

    ctx.obj = CtxObject

    bundle = yaml.load_all(bundle, Loader=yaml.CSafeLoader)
    kind_prefixes = dict()

    file_path = os.path.abspath(output_path)
    for doc in bundle:
        if not doc:
            continue

        this_kind = doc['kind']

        prefix = '%-.2d--' % kind_prefixes.setdefault(this_kind, len(kind_prefixes))

        doc_name = f'{prefix}{doc["kind"]}--{doc["metadata"]["name"]}.yaml'
        doc_path = f'{file_path}/{doc_name}'

        if verbose:
            click.echo(f'writing {doc["kind"]}/{doc["metadata"]["name"]}.yaml to {output_path}/{doc_name}')

        with open(doc_path, 'w') as fh:
            yaml.dump(doc, fh, Dumper=yaml.CSafeDumper)
